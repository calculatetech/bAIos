"""Small DHCP/ARP/TFTP peer for the official 86Box Local Switch raw-frame seam."""
import socket
import struct
import threading

GROUP=('239.255.86.86',8086)
SERVER=socket.inet_aton('192.168.86.1')
CLIENT=socket.inet_aton('192.168.86.10')
MAC=bytes.fromhex('020000008601')


def checksum(data):
    if len(data)&1:data+=b'\0'
    value=sum(struct.unpack('!%dH'%(len(data)//2),data))
    while value>>16:value=(value&65535)+(value>>16)
    return (~value)&65535


class Peer:
    def __init__(self,payload,fail=False):
        self.payload,self.fail=payload,fail
        self.events=[]
        self.stop=threading.Event()
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP)
        self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        self.socket.bind(('',8086))
        self.socket.setsockopt(socket.IPPROTO_IP,socket.IP_ADD_MEMBERSHIP,socket.inet_aton(GROUP[0])+socket.inet_aton('0.0.0.0'))
        self.socket.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_TTL,1)
        self.socket.settimeout(.25)
        self.thread=threading.Thread(target=self.run)

    def __enter__(self):self.thread.start();return self
    def __exit__(self,*unused):self.stop.set();self.thread.join();self.socket.close()

    def udp(self,dstmac,dstip,sport,dport,body):
        udp=struct.pack('!HHHH',sport,dport,8+len(body),0)+body
        ip=struct.pack('!BBHHHBBH4s4s',0x45,0,20+len(udp),0,0,64,17,0,SERVER,dstip)
        ip=ip[:10]+struct.pack('!H',checksum(ip))+ip[12:]
        self.socket.sendto(dstmac+MAC+b'\x08\x00'+ip+udp,GROUP)

    def frame(self,data):
        if len(data)<42 or data[6:12]==MAC:return
        dst,src=data[:6],data[6:12]
        if data[12:14]==b'\x08\x06':
            arp=data[14:]
            if len(arp)>=28 and arp[6:8]==b'\0\1' and arp[24:28]==SERVER:
                reply=struct.pack('!HHBBH',1,0x800,6,4,2)+MAC+SERVER+arp[8:18]
                self.socket.sendto(src+MAC+b'\x08\x06'+reply,GROUP)
                self.events.append('ARP')
            return
        if data[12:14]!=b'\x08\x00' or data[23]!=17:return
        ihl=(data[14]&15)*4
        at=14+ihl
        sport,dport,length,_=struct.unpack('!HHHH',data[at:at+8])
        body=data[at+8:at+length]
        ip=data[26:30]
        if dport==67 and len(body)>=240 and body[236:240]==b'\x63\x82\x53\x63':
            options={};at=240
            while at<len(body):
                kind=body[at];at+=1
                if kind==255:break
                if not kind:continue
                count=body[at];at+=1;options[kind]=body[at:at+count];at+=count
            kind=options.get(53,b'\0')[0]
            if kind not in (1,3):return
            result=bytearray(body[:236]);result[0]=2
            result[16:20]=CLIENT;result[20:24]=SERVER
            result[108:236]=b'baios.nbp\0'.ljust(128,b'\0')
            opt=b'\x63\x82\x53\x63'+bytes((53,1,2 if kind==1 else 5))
            opt+=bytes((54,4))+SERVER+bytes((1,4))+b'\xff\xff\xff\0'
            opt+=bytes((3,4))+SERVER+bytes((51,4))+struct.pack('!I',3600)+b'\xff'
            self.udp(b'\xff'*6,b'\xff'*4,67,68,bytes(result)+opt)
            self.events.append('OFFER' if kind==1 else 'ACK')
        elif dport in (69,2000) and len(body)>=2:
            op=struct.unpack('!H',body[:2])[0]
            if op==1:
                self.events.append('RRQ:'+body[2:].split(b'\0')[0].decode('ascii','replace'))
                if self.fail:
                    self.udp(src,ip,2000,sport,b'\0\5\0\1Fixture unavailable\0')
                    self.events.append('ERROR')
                else:self.udp(src,ip,2000,sport,b'\0\3\0\1'+self.payload[:512])
            elif op==4:
                block=struct.unpack('!H',body[2:4])[0]
                self.events.append('TFTP ACK %d'%block)
                start=block*512
                if start<=len(self.payload):
                    self.udp(src,ip,2000,sport,struct.pack('!HH',3,block+1)+self.payload[start:start+512])

    def run(self):
        while not self.stop.is_set():
            try:data,_=self.socket.recvfrom(65536)
            except socket.timeout:continue
            self.frame(data)

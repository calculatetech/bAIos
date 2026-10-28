; Resolve the shared owner from this include root, independently of shell cwd.
%ifndef PRESARIO_SHARED_OWNER
%define PRESARIO_SHARED_OWNER
%pathsearch PRESARIO_SOURCE "shared-owner.inc"
%strlen PRESARIO_SOURCE_LENGTH PRESARIO_SOURCE
%substr PRESARIO_SOURCE_DIRECTORY PRESARIO_SOURCE 1,(PRESARIO_SOURCE_LENGTH-16)
%macro presario_shared 1
%strcat %%source PRESARIO_SOURCE_DIRECTORY,"../../shared/src/",%1
%include %%source
%endmacro
%endif

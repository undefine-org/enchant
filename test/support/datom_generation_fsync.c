/* Fixed synthetic paths only. Stop the whole writer at real IO boundaries. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static int (*real_sync)(int);
static ssize_t (*real_write)(int,const void *,size_t);
static const char *root,*boundary,*ack;
static atomic_flag stopped=ATOMIC_FLAG_INIT;
__attribute__((constructor)) static void initialize(void) {
 real_sync=dlsym(RTLD_NEXT,"fsync"); real_write=dlsym(RTLD_NEXT,"write");
 root=getenv("DATOM_CRASH_ROOT"); boundary=getenv("DATOM_CRASH_BOUNDARY"); ack=getenv("DATOM_CRASH_ACK");
}
static int path_of(int fd,char *path) {
 if (!root || !boundary || !ack || strncmp(root,"/build/generation-crash-fixtures/",strlen("/build/generation-crash-fixtures/"))) return 0;
 char descriptor[64]; snprintf(descriptor,sizeof descriptor,"/proc/self/fd/%d",fd);
 ssize_t n=readlink(descriptor,path,PATH_MAX-1); if(n<0)return 0; path[n]=0;
 return !strncmp(path,root,strlen(root)) && (path[strlen(root)]=='/' || !path[strlen(root)]);
}
static void stop_here(void) {
 if(atomic_flag_test_and_set(&stopped))return;
 int output=open(ack,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
 if(output<0 || real_write(output,boundary,strlen(boundary))!=(ssize_t)strlen(boundary))_exit(96);
 close(output); raise(SIGSTOP); _exit(97);
}
ssize_t write(int fd,const void *bytes,size_t count) {
 char path[PATH_MAX],target[PATH_MAX];
 if(path_of(fd,path) && !strcmp(boundary,"marker-created")) {
  snprintf(target,sizeof target,"%s/generation/firm/library.fjall/.bl-datom-create",root);
  if(!strcmp(path,target))stop_here();
  snprintf(target,sizeof target,"%s/generation/firm/library.fjall/.bl-datom-create.pending",root);
  if(!strcmp(path,target))stop_here();
 }
 return real_write(fd,bytes,count);
}
int fsync(int fd) {
 int result=real_sync(fd); if(result)return result;
 char path[PATH_MAX],target[PATH_MAX],marker[PATH_MAX],version[PATH_MAX];
 if(!path_of(fd,path))return result;
 snprintf(target,sizeof target,"%s/generation/firm/library.fjall",root);
 snprintf(marker,sizeof marker,"%s/generation/firm/library.fjall/.bl-datom-create",root);
 snprintf(version,sizeof version,"%s/generation/firm/library.fjall/version",root);
 if(!strcmp(boundary,"marker-synced")) {
  if(!strcmp(path,marker))stop_here();
  snprintf(marker,sizeof marker,"%s/generation/firm/library.fjall/.bl-datom-create.pending",root);
  if(!strcmp(path,marker))stop_here();
 }
 if(!strcmp(boundary,"marker-retired") && !strcmp(path,target) && access(marker,F_OK)!=0 && access(version,F_OK)==0)stop_here();
 snprintf(target,sizeof target,"%s/WRITE-ACK.json",root);
 if(!strcmp(boundary,"data-ack") && !strcmp(path,root) && access(target,F_OK)==0)stop_here();
 return result;
}

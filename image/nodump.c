// LD_PRELOAD: non-dumpable after exec (exec resets the flag), so a crash skips the core dump and its wait for every
// thread to stop, which can hang a KVM guest's process for good (#31).
#include <sys/prctl.h>

__attribute__((constructor)) static void nodump(void) { prctl(PR_SET_DUMPABLE, 0, 0, 0, 0); }

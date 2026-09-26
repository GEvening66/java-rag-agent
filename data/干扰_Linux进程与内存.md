# Linux 进程与内存（干扰文档 · 术语与 Java 并发重叠）

## 进程与线程
Linux 中进程和线程都由 task_struct 描述，线程本质上是可以共享地址空间的轻量级进程。
创建进程用 fork，创建线程用 pthread_create，两者最终都调用 clone 系统调用，只是共享标志不同。
线程共享：地址空间、文件描述符、信号处理器；线程私有：栈、寄存器、程序计数器。
上下文切换开销：进程 > 线程 > 协程。

## 虚拟内存
每个进程有独立的虚拟地址空间，通过页表映射到物理内存。
页大小通常为 4KB，大页（HugePage）可以到 2MB 或 1GB，用于减少 TLB miss。
用户空间与内核空间按 3:1 划分（32 位系统），64 位系统地址空间极大。
内存映射（mmap）可以把文件直接映射进地址空间，避免用户态与内核态的数据拷贝。

## OOM Killer
当物理内存和交换分区都被耗尽时，内核的 OOM Killer 会挑选一个进程杀掉。
选择依据是 oom_score：占用内存越多、优先级越低，分数越高，越容易被杀。
可以通过 /proc/[pid]/oom_score_adj 调整优先级，或给关键进程设为 -1000 以豁免。
容器环境下，cgroup 内存限制触发的 OOM 只影响该容器。

## 内存指标
`free -h` 查看总体内存；available 才是真正可用的估计值，buff/cache 可回收。
`top` / `htop` 按内存排序观察进程；`pmap` 查看进程地址空间映射。
Page Cache 会尽量占用空闲内存以加速 IO，这不是内存泄漏。
Swap 使用率持续升高说明物理内存不足，会导致系统抖动。

## 常用排查命令
CPU：`top`、`pidstat`、`perf top`。
内存：`vmstat`、`smem`、`/proc/meminfo`。
IO：`iostat`、`iotop`、`lsof`。
网络：`ss`、`netstat`、`tcpdump`。
进程：`ps -ef`、`pstree`、`strace`。

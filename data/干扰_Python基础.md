# Python 基础（干扰文档 · 与 Java 术语高度重叠）

## 字典与哈希表
Python 的 dict 底层同样使用哈希表实现，通过开放寻址法处理冲突（与 Java HashMap 的拉链法不同）。
dict 在 Python 3.7 之后保证插入顺序，内部用紧凑数组存储索引。
当装载因子超过 2/3 时，CPython 会触发扩容，把容量调整为当前使用量的 3 倍以上，并重新插入所有键值对。
键必须是可哈希对象：如果自定义类重写了 `__eq__`，必须同时实现 `__hash__`，否则该类的实例不可哈希。
这与 Java 中"重写 equals 必须重写 hashCode"的约定思路一致。

## 垃圾回收
CPython 使用引用计数为主、分代回收为辅的策略。
每个对象维护一个引用计数，计数归零时立即释放。
循环引用需要靠分代回收器处理：把对象分为三代，越年轻的对象扫描越频繁，这点与 JVM 分代收集类似。
可以通过 `gc` 模块手动触发回收，或调整阈值。
`__del__` 方法在对象被回收时调用，但它的行为不确定，类似 JVM 中已被废弃的 finalize。

## 异常处理
Python 用 try / except / else / finally 处理异常，语法与 Java 的 try / catch / finally 相似但更灵活。
所有异常都继承自 BaseException，业务异常通常继承 Exception。
与 Java 的受检异常不同，Python 没有 checked exception 机制，任何异常都不强制捕获。
`raise` 相当于 Java 的 throw，`raise ... from ...` 可以保留异常链。

## 并发
Python 的 threading 模块受 GIL（全局解释器锁）限制：同一时刻只有一个线程执行字节码，
因此多线程适合 I/O 密集任务，CPU 密集任务应使用 multiprocessing。
这一点与 Java 的多线程模型完全不同——Java 的线程可以真正并行执行。
`asyncio` 提供协程与事件循环，适合高并发 I/O，但它是单线程模型。

## 内存管理
Python 对象都在堆上分配，由解释器统一管理，没有栈上分配的概念。
可以用 `sys.getsizeof` 查看对象占用，用 `tracemalloc` 追踪内存分配。
内存泄漏通常来自全局缓存、循环引用或 C 扩展。

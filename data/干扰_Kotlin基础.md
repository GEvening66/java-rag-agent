# Kotlin 基础（干扰文档 · 同为 JVM 语言）

## 空安全
Kotlin 在类型系统层面区分可空类型与非空类型：`String` 不可为空，`String?` 可以为空。
访问可空类型必须使用安全调用 `?.`、非空断言 `!!` 或 Elvis 运算符 `?:`，否则编译不通过。
这套设计在编译期消除了大量空指针问题，而 Java 只能在运行时抛 NullPointerException。

## 集合
Kotlin 的集合分为只读（List、Set、Map）与可变（MutableList 等）两套接口。
`listOf()` 返回只读列表，`mutableListOf()` 返回可变列表。
底层在 JVM 上直接复用 java.util 的实现，因此性能特征与 Java 集合一致。
Kotlin 还提供大量扩展函数：`map`、`filter`、`groupBy`、`associate` 等，比 Java 的 Stream API 更简洁。

## 协程
协程是 Kotlin 处理异步的主要方式，用 `suspend` 关键字标记挂起函数。
协程比线程更轻量：一个线程可以运行成千上万个协程，切换开销极低。
`launch` 用于启动不返回结果的协程，`async` 用于需要返回值的场景，通过 `await` 获取结果。
结构化并发要求所有协程都在某个作用域（CoroutineScope）内启动，作用域取消时子协程一并取消。
这与 Java 的虚拟线程（Virtual Threads）目标相似，但实现机制不同。

## 数据类与密封类
`data class` 自动生成 equals、hashCode、toString、copy，相当于 Java 的 record 或手写 POJO。
`sealed class` 表示受限的继承结构，所有子类必须在同一文件中声明，配合 when 表达式可以做穷尽检查。

## 与 Java 的互操作
Kotlin 可以调用 Java 代码，反之亦然。
Java 中调用 Kotlin 的顶层函数会生成 FileKt 类；Kotlin 的属性会被编译成 getter/setter。
平台类型（如从 Java 传过来的 String!）不做空检查，需要开发者自行判断。

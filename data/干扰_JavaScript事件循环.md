# JavaScript 事件循环与内存（干扰文档 · 异步与 GC 概念重叠）

## 单线程模型
JavaScript 在主线程上是单线程的：同一时刻只执行一段代码，没有多线程竞争问题。
耗时操作（网络请求、文件 IO、定时器）交给宿主环境（浏览器或 Node.js）的线程池处理，
完成后把回调放入任务队列，等主线程空闲时执行。
这就是"事件循环"（Event Loop）的核心机制，与 Java 的多线程并发模型完全不同。

## 宏任务与微任务
宏任务（macrotask）：setTimeout、setInterval、I/O、UI 渲染。
微任务（microtask）：Promise.then、queueMicrotask、MutationObserver。
每执行完一个宏任务，会把微任务队列**全部清空**，然后才进入下一个宏任务。
因此 Promise 的回调总比 setTimeout 先执行，即使延时为 0。
Node.js 中还有 process.nextTick，优先级高于 Promise 微任务。

## 垃圾回收
V8 引擎采用分代回收：新生代用 Scavenge 算法（复制），老生代用标记-清除与标记-整理。
与 JVM 的分代收集思路高度一致，但 V8 没有暴露给开发者调优的复杂参数。
常见内存泄漏原因：意外的全局变量、未清理的定时器、闭包持有大对象、DOM 引用未释放。
可以用 Chrome DevTools 的 Memory 面板抓取堆快照对比，或 Performance 面板观察 GC 频率。

## Promise 与 async/await
Promise 有三种状态：pending、fulfilled、rejected，状态一旦改变不可逆。
`async` 函数返回 Promise；`await` 会暂停当前函数，把后续代码放入微任务队列。
未捕获的 Promise 拒绝会导致 unhandledrejection，在 Node.js 中可能终止进程。

## 模块与工程化
CommonJS 用 require/module.exports，同步加载，Node.js 默认。
ES Module 用 import/export，静态分析友好，支持 tree-shaking。
打包工具：webpack、vite、rollup。Vite 开发态用原生 ESM + 按需编译，启动极快。

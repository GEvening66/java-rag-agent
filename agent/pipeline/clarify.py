"""澄清追问：宽泛问题先反问澄清（agent 的"规划"要素）。"""
from . import tools

BROAD_WORDS = ("讲讲", "介绍", "说一下", "概述", "说说", "谈谈")
MIN_SPECIFIC_LEN = 8  # 去空白后短于此长度视为意图不明

CLARIFY_TEXT = (
    "这个问题比较宽泛，你想具体了解哪个方面？"
    "（比如：存储结构 / 负载因子与扩容 / 线程安全 / ...）"
)


def needs_clarification(question):
    """判断问题是否宽泛：含宽泛动词，或过短。"""
    if any(w in question for w in BROAD_WORDS):
        return True
    return len("".join(question.split())) < MIN_SPECIFIC_LEN


def run(index, max_turns=3):
    """交互式澄清问答循环（有界）。"""
    print("Agent：你好！我是 Java 学习助手，有什么想问的？（输入 exit 退出）\n")
    for _ in range(max_turns):
        question = input("你：").strip()
        if question in ("exit", "quit", "退出"):
            break
        if needs_clarification(question):
            print("Agent：" + CLARIFY_TEXT)
            extra = input("你：").strip()
            if extra in ("exit", "quit", "退出"):
                break
            # 记忆：把澄清内容拼进问题，检索才有靶子
            question = f"{question}，具体是：{extra}"
        print("Agent：" + tools.run(question, index) + "\n")
    print("Bye!")

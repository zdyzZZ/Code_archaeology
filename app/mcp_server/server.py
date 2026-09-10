# -*- coding: utf-8 -*-
"""MCP Server：把 git / GitHub 能力暴露成工具。

⚠️ 工具设计你自己做 —— "必须手写"清单里的一项。

工具设计是有讲究的，面试会问：

1. **粒度**：给一个万能的 run_git(cmd) 还是给一组语义明确的工具？
   前者省事但模型容易乱用、也没法做权限控制；后者啰嗦但可控。
2. **返回体积**：git log 可能返回几万行。工具要不要自己截断？
   截断了模型怎么知道还有更多？（提示：返回里带 has_more 和游标）
3. **错误信息**：文件不存在、repo 太大、限流——这些要以模型能理解的方式返回，
   不是抛异常。模型需要能据此改变策略。

计划中的工具：
    git_blame(repo, file, start, end)     -> 穿透版 blame 结果
    git_log(repo, file, limit)            -> 变更链
    git_diff(repo, sha, file)             -> 单次改动内容
    read_file(repo, file, sha)            -> 某个版本的文件内容
    search_issues(repo, query, limit)     -> issue 检索
    get_pr(repo, number)                  -> PR 正文 + review 评论
    get_commit(repo, sha)                 -> commit 详情

TODO:
  - [ ] 用 mcp 的 Server / FastMCP 定义上面这些工具
  - [ ] 每个工具的入参用 Pydantic 约束，别放任意字符串
  - [ ] 返回统一结构，超长时截断并给出游标
  - [ ] stdio 传输先跑通，再考虑 Streamable HTTP

参考：
  https://py.sdk.modelcontextprotocol.io/zh/get-started/
  https://modelcontextprotocol.io/
"""


def build_server():
    """TODO"""
    raise NotImplementedError


if __name__ == '__main__':
    # TODO: 用 MCP Inspector 连上来测
    pass

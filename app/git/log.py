from pathlib import Path
from app.git.repo import run


def commit_info(repo: Path, sha: str) -> dict:
    """拿某个 commit 的完整 message（标题 + 正文 + 日期 + 修改人）。"""
    out = run(['git', 'log', '-1', '--format=%ad%n%an%n%B', '--date=short', sha], cwd=repo).strip()
    date, author, message = out.split('\n', 2)
    return {'sha': sha, 'date': date, 'author': author, 'message': message}


def commit_diff(repo: Path, sha: str,file_path:Path) -> str:
    """拿到这次提交对这个文件的改动，截断到 3000 字左右"""
    out = run([
        "git","show","--format=","--no-color",sha,"--",file_path.as_posix(),], cwd=repo).strip()
    if len(out) > 3000:
        return out[:3000] + "\n...[diff truncated]"
    elif not out:
        return "(这个 commit 对该文件没有 diff)"
    return out


def line_history(repo: Path, file_path:Path,start:int,end:int) -> list[dict]:
    '''追踪历史链'''
    out = run(['git','log','-L',f'{start},{end}:{file_path}','--format=@@COMMIT %H'],cwd=repo)
    history = []

    for chunk in out.split("@@COMMIT "):
        chunk = chunk.strip()
        if not chunk:
            continue

        sha, diff = chunk.split("\n", 1)

        history.append({
            "sha": sha.strip(),
            "diff": diff.strip(),
        })
    return history

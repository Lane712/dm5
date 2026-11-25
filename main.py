from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import json,re,os

from py_mini_racer import MiniRacer

DM5_SCHEMA = "https://"
DM5_HOST = "m.dm5.com"

SCRIPT_PATTERN = r"<script\b[^>]*>\s*eval([\s\S]*?)<\/script>"
IMAGES_PATTERN = r"var\s+newImgs\s*=\s*(\[[\s\S]*\]);"

HEADERSFORHTML = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://m.dm5.com/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:153.0) Gecko/20100101 Firefox/153.0",
    "Sec-Fetch-Dest": "document",
}

HEADERFORJPG = {
    "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
    "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
    "Referer": "https://m.dm5.com/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:153.0) Gecko/20100101 Firefox/153.0",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "cross-site",
}

class Chapter:
    """章节"""
    def __init__(self, url: str, name: str = "", title: str = ""):
        self.url = url
        self.name = name
        self.title = title

    
class Manga:
    """漫画"""
    def __init__(self, title: str, desc: str = "", status: str = "", tags: set = ..., dm5_url: str = "", cover_url: str = "", chapters: list[Chapter] = []):
        self.title = title
        self.desc = desc
        self._tags = set()
        self.status = status
        self.dm5_url = dm5_url
        self.cover_url = cover_url
        self.chapters = chapters

    @property
    def tags(self):
        return list(self._tags)

    @tags.setter
    def tags(self, value):
        if isinstance(value, str):
            value = [value]
        self._tags.update(value)

    @property
    def jsonform(self) -> dict[str, any]:
        '''适配 json 写入'''
        manga = self.detail_dict
        manga["chapters"] = self.chapters_list

        return manga

    @property
    def detail_dict(self) -> dict[str, any]:
        return {
            "title": self.title,
            "desc": self.desc,
            "tags": list(self.tags),
            "status": self.status,
            "dm5_url": self.dm5_url,
            "cover_url": self.cover_url
        }

    @property
    def chapters_list(self) -> list[dict[str, any]]:
        chapters = []
        for chapter in self.chapters:
            chapters.append(chapter.__dict__)
        return chapters

    def load_chapters(self, chapter_list: list[dict[str,any]]):
        chapters = []
        for chapter in chapter_list:
            chapters.append(Chapter(**chapter))
        self.chapters = chapters


class DM5:
    def __init__(self, output_dir: str = "", temp_dir: str = "temp"):
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.html_dir = self.temp_dir.joinpath("html")
        self.json_dir = self.temp_dir.joinpath("json")
        self.data_file = self.output_dir.joinpath("data.json")
        self.mkdirs()
        self.ctx = MiniRacer()

    def mkdirs(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.html_dir.mkdir(parents=True, exist_ok=True)
        self.json_dir.mkdir(parents=True, exist_ok=True)

    def load_manga(self):
        pass

    # def load_chapters(self, manga: Manga):
    #          # 漫画 chapters 保存路径
    #         fp_manga = self.json_dir.joinpath(manga.title + ".json")
    #         if fp_manga.exists():
    #             with open(fp_manga, 'r', encoding="utf-8") as f:
    #                 manga.load_chapters(json.load(f))
    #                 return manga
    #         else:
    #             return self.get_chapters(manga)

    def update(self, *mangas: Manga, backup: bool = True):
        """更新漫画数据
        
        """
        # 读取
        try:
            with open(self.data_file, "r+", encoding='utf-8') as f:
                manga_list = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            manga_list = []
        # 备份
        if backup:
            with open(self.data_file.as_posix() + ".bak", "w", encoding="utf-8") as f:
                f.write(json.dumps(manga_list, ensure_ascii=False, indent=2))
        # 临时集合
        manga_set = set()
        for manga in manga_list:
            manga_set.add(manga.get("title"))
        # 只添加新的漫画 ## TODO: 还是应该使用数据库。。。重复数据好难处理。。。 
        for manga in mangas:
            if manga.title in manga_set: # 避免添加重复数据
                continue
            manga_list.append(manga.detail_dict)
        # 写入数据文件
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(manga_list, f, ensure_ascii=False, indent=2)

        return len(manga_list)

    def search(self, kwd: str = "蓝箱", cached: bool = True) -> list[Manga]:
        """搜索

        """
        try:
            # 搜索结果缓存路径
            ## TODO: 接入数据库？保存搜索历史...更新时按照最大的相同字先搜索，确保少次搜索可以拿到新的 dm5_url, status, 
            fp_search_html = self.html_dir.joinpath(f"{kwd}_搜索结果.html")
            if fp_search_html.exists() and cached: # 默认使用缓冲
                raise FileExistsError
            # 发起搜索请求
            res = requests.get(urljoin(DM5_SCHEMA + DM5_HOST, "search"), params={"title": kwd, "language": 1}, headers=HEADERSFORHTML)
            res.raise_for_status()
            html = res.text
            with open(fp_search_html, "w", encoding="utf-8") as f:
                f.write(html)
        except FileExistsError:
            with open(fp_search_html, "r", encoding="utf-8") as f:
                html = f.read()
            print(f"{fp_search_html} 已存在，HTML文件读取成功")
        # 解析 HTML
        soup = BeautifulSoup(html, "html.parser")
        book_list_ul = soup.find("ul", attrs={"class": "book-list"})
        if book_list_ul:
            book_list = book_list_ul.find_all("li")
            if not book_list:
                raise NameError()
        # 收集漫画信息
        mangas = []
        for book in book_list:
            manga = None
            # 标题
            title_p = book.find("p", attrs={"class": "book-list-info-title"})
            if title_p:
                manga = Manga(title_p.get_text(strip=True))
            if manga is None:
                continue
            url_a = book.find("a", attrs={"title": True})
            # 漫画 dm5 链接
            if url_a:
                manga.dm5_url = urljoin(DM5_SCHEMA + DM5_HOST, url_a.get("href"))
            # 封面
            cover_img = book.find("img", attrs={"class": "book-list-cover-img"})
            if cover_img:
                manga.cover_url = cover_img.get("src")
            # 简介
            desc_p = book.find("p", attrs={"class": "book-list-info-desc"})
            if desc_p:
                manga.desc = desc_p.get_text()
            # 标签
            tags_span = book.find("span", attrs={"class": "book-list-info-bottom-item"})
            if tags_span:
                manga.tags = tags_span.get_text(strip=True) ## TODO: 会残留上次的 tag 不能在函数列表初始化 set()
            # 状态
            status_span = book.find("span", attrs={"class": "book-list-info-bottom-right-font"})
            if status_span:
                manga.status = status_span.get_text(strip=True)

            print(manga.detail_dict) # 测试用
            mangas.append(manga)

        self.update(*mangas)
        return mangas

    def get_chapters(self, manga: Manga, cached: bool = True):
        """保存

        """
        # 漫画 chapters 保存路径
        fp_manga = self.json_dir.joinpath(manga.title + ".json")
        if fp_manga.exists() and cached:
            with open(fp_manga, 'r', encoding="utf-8") as f:
                manga.load_chapters(json.load(f))
                return manga
        # 获取带有漫画目录的 html
        try:
            # 漫画 html 路径
            fp_html = self.html_dir.joinpath(manga.title + ".html")
            if fp_html.exists() and cached:
                raise FileExistsError
            # 获取 html
            res = requests.get(manga.dm5_url, headers=HEADERSFORHTML)
            res.raise_for_status()
            html = res.text
            with open(fp_html, "w", encoding="utf-8") as f:
                f.write(html) # 保存 html  
        except FileExistsError:
            with open(fp_html, "r", encoding="utf-8") as f:
                html = f.read() # 读取 html
            print(f"{fp_html} 已存在，HTML文件读取成功")
        # 解析 HTML
        soup = BeautifulSoup(html, "html.parser")
        chapter_uls = soup.find_all("ul", attrs={"class": "detail-list-1 detail-list-select"})
        if chapter_uls:
            # 递归寻找 chapteritems
            for chapter_ul in chapter_uls:
                try:
                    # 获取 chapteritems
                    chapteritems = chapter_ul.find_all("a")
                    if chapteritems:
                        for chapteritem in chapteritems:
                            # 写入 chapter 数据
                            manga.chapters.append(Chapter(
                                url = urljoin(DM5_SCHEMA + DM5_HOST, chapteritem.get("href")),
                                name =  chapteritem.get_text(strip=True),
                                title =  chapteritem.get("title")
                            ))
                            print(chapteritem.get_text())
                except Exception as e: # 出错时写入，避免丢失全部内容
                    print(e)
                    with open(fp_manga, "w", encoding='utf-8') as f:
                        f.write(json.dumps(manga.chapters_list, ensure_ascii=False, indent=2))

        with open(fp_manga, "w", encoding='utf-8') as f:
            f.write(json.dumps(manga.chapters_list, ensure_ascii=False, indent=2))

        return manga

    def download(self, manga: Manga, caps: tuple | list = ..., coverd: bool = False):
        """下载

        Args:
            manga (Manga): 需要下载的漫画
            caps (tuple): 下载的章节，如果不设置默认下载全部，
            coverd (bool): 是否覆盖已经下载的漫画文件
        
        """
        fp_chapters = self.temp_dir.joinpath(manga.title)
        fp_chapters.mkdir(parents=True, exist_ok=True)

        # 加载 chapters 数据
        if len(manga.chapters) == 0:
            self.get_chapters(manga)

        for chapter in manga.chapters:
            # 跳过未选章节
            c_index_m = re.search(r"^第([\d]+)话$", chapter.name)
            if c_index_m:
                c_index = int(c_index_m.group(1))
                if isinstance(caps, tuple):
                    if c_index not in range(*caps):
                        continue
                elif isinstance(caps, list):
                    if c_index not in caps:
                        continue
            # 当前话数漫画文件存放目录
            fp_chapter = fp_chapters.joinpath(chapter.name)
            fp_chapter.mkdir(parents=True, exist_ok=True)
            # 获取 html
            res = requests.get(chapter.url, headers=HEADERSFORHTML)
            res.raise_for_status()
            html = res.text
            with open(fp_chapter.joinpath(manga.title +"-"+ chapter.name + ".html"), "w", encoding="utf-8") as f:
                f.write(html)
            # 从 html 的内置脚本中提取出 images
            script_m = re.search(SCRIPT_PATTERN, html)
            if script_m:
                script = script_m.group(1)
            # 执行 js 脚本，获取实际下载链接
            plain = self.ctx.eval(script)
            urls_m = re.search(IMAGES_PATTERN, plain)
            if urls_m:
                urls = json.loads(urls_m.group(1).replace("\'", "\"")) # json.loads() 不认单引号
                with open(fp_chapter.joinpath("images.json"), "w", encoding="utf-8") as f:
                    json.dump(urls, f, ensure_ascii=False, indent=2)
                if len(urls):
                    for url in urls:
                        # 解析下载链接
                        filename = os.path.basename(url.split("?")[0])
                        index, ext = re.search(r"^(\d+)_\d+(\.\w+)$", filename).groups()
                        fp_jpg = fp_chapter.joinpath(f"{int(index):03d}" + ext)
                        if fp_jpg.exists() and not coverd:
                            continue # 存在时跳过
                        res = requests.get(url, headers=HEADERFORJPG)
                        res.raise_for_status()
                        with open(fp_jpg, "wb") as f:
                            f.write(res.content)
                        print(fp_jpg, os.stat(fp_jpg).st_size // 1024, "KB")


if __name__ == "__main__":
    dm5 = DM5()
    mangas = dm5.download(Manga("蓝箱"), (45,60))

    
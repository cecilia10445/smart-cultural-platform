import re

import jieba


def tokenize(text):
    normalized = re.sub(r"\s+", " ", str(text).lower())
    return [
        part
        for part in jieba.lcut(normalized)
        if part.strip() and not re.fullmatch(r"\W+", part)
    ]

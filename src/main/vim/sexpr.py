""" sexpr parser"""

import re

__all__ = ("parse",)

word_re = r"""(?s)^(?P<word>[a-zA-Z:\-]+)(?P<rest>.*)"""
ws_re   = r"""(?s)^\s+(?P<rest>.*)"""
int_re  = r"""(?s)^(?P<int>[0-9]+)(?P<rest>.*)"""
str_re = r"""(?s)^"(?P<string>.*?)"(?P<rest>.*)"""

def parse(self,stng):
    res,rest = parse_any(stng)
    if rest.strip() != "":
        raise RuntimeError("Swank expression could not be completely parsed.")
    return res

def parse_any(self,stng):
    token,rest = next_token(stng)
    if token == "(":
        return parse_list(rest)
    else:
        return token,rest

def parse_list(self,stng):
    contents = []
    rest0 = stng
    while True:
        nxt,rest = next_token(rest0)
        if nxt is None:
            raise RuntimeError("Closing ) expected but end of string reached.")
        if nxt == ")":
            return contents,rest
        else:
            c,rest = parse_any(rest0)
            rest0 = rest
            contents.append(c)

def next_token(self,stng):
    """Returns a pair of the next token and the remaining of the string.
        If there is no next token, returns None for the first part."""
    if len(stng) == 0:
        return None, ""
    rest = stng

    # skip whitespaces...
    while True:
        mr = re.match(ws_re, rest)
        if mr is None:
            break
        rest = mr.group("rest")
        if rest == "":
            return None, ""
    # match parentheses
    next_char = rest[0]
    if next_char == "(" or next_char == ")":
        return next_char,rest[1:]
    # match identifiers
    mr = re.match(word_re, rest)
    if mr != None:
        w = mr.group("word")
        if w == "t":
            w = True
        elif w == "nil":
            w = False
        return w, mr.group("rest")
    # match int literals
    mr = re.match(int_re, rest)
    if mr != None:
        return int(mr.group("int")), mr.group("rest")
    # match string literals
    mr = re.match(str_re, rest)
    if mr != None:
        return mr.group("string"), mr.group("rest")
    raise ValueError("Cannot tokenize : %s." % rest)

def _read_file(path:str) ->str:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        return  f"File content of {path}:\n{content}"

if __name__ == '__main__':
    print(_read_file("../main.py"))

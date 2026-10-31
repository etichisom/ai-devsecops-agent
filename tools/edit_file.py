import os.path


def edit_file(path:str, old_text:str, new_text: str):
    if os.path.exists(path):
        with open(path,'r', encoding='utf-8') as f:
            content = f.read()
            if old_text not in content:
                return f"text not found in file:{old_text}"
            content = content.replace(old_text, new_text)

            with open(path,'w', encoding='utf-8') as w:
                w.write(content)
    else:
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name,exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_text)

if __name__ == '__main__':
    edit_file(
        path='../random_file.txt',
        old_text='yes this is the file',
        new_text="Print hello boy"
    )

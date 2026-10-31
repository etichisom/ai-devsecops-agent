import os.path


def _list_files(path:str) -> str:
    if not os.path.exists(path):
        return f"Path not found; {path}"

    items = []
    for item in os.listdir(path):
        item_path = os.path.join(path, item)
        if os.path.isdir(item_path):
            items.append(f"[Dire] {item}")
        else:
            items.append(f'[File] {item}')

    if not items:
        return  f"Empty directory: {path}"

    return  f"Contents of {path}:\n" + "\n".join(items)



if __name__ == '__main__':
    print(_list_files('..'))

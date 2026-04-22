import os

def get_dir_size(path):
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += get_dir_size(entry.path)
    except PermissionError:
        pass
    except FileNotFoundError:
        pass
    except OSError:
        pass
    return total

def scan_target(target):
    print(f"Scanning target: {target}")
    if os.path.exists(target):
        dirs = []
        for entry in os.listdir(target):
            p = os.path.join(target, entry)
            if os.path.isdir(p):
                size_mb = get_dir_size(p) / (1024*1024)
                dirs.append((entry, size_mb))
        
        dirs.sort(key=lambda x: x[1], reverse=True)
        for name, size in dirs:
            if size > 10:  # Only show folders larger than 10MB
                print(f"  {name}: {size:.2f} MB")
    else:
        print("  Not found.")
    print("-" * 30)

scan_target(r"C:\Users\ASUS\.gemini\antigravity")
scan_target(r"C:\Users\ASUS\.cache")
scan_target(r"C:\Users\ASUS\AppData\Local\Temp")

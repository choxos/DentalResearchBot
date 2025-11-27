import re

def markdown_to_telegram(text: str) -> str:
    """
    Convert standard Markdown to Telegram-friendly format with emojis.
    
    Conversions:
    - # Header 1 -> 📌 *Header 1*
    - ## Header 2 -> 🔹 *Header 2*
    - ### Header 3 -> 🔸 *Header 3*
    - **bold** -> *bold* (Telegram uses * for bold in Markdown legacy)
    - - list -> • list
    """
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        # Headers
        if line.startswith('# '):
            content = line[2:].strip()
            line = f"📌 *{content}*"
        elif line.startswith('## '):
            content = line[3:].strip()
            line = f"🔹 *{content}*"
        elif line.startswith('### '):
            content = line[4:].strip()
            line = f"🔸 *{content}*"
        elif line.strip().startswith('- '):
            line = line.replace('- ', '• ', 1)
            
        # Bold: **text** -> *text*
        line = re.sub(r'\*\*(.*?)\*\*', r'*\1*', line)
        
        formatted_lines.append(line)
        
    return '\n'.join(formatted_lines)



import os

path = r'c:\Users\HP\OneDrive\Desktop\siksha_setuwu\core\templates\core\course_detail.html'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if '{% if' in line and 'user_review.rating|add:0==i|add:0 %}checked{% endif %}>' in line:
        # This shouldn't happen if it's on two lines, but I'll handle both cases
        new_lines.append(line)
    elif '{% if' in line and 'id="rate-{{ i }}"' in line:
        # Check if next line is the broken part
        current_idx = len(new_lines)
        new_lines.append(line.replace('{% if', '').rstrip() + ' ')
    elif 'user_review.rating|add:0==i|add:0 %}checked{% endif %}>' in line:
        if new_lines and new_lines[-1].strip().endswith('id="rate-{{ i }}"'):
            prev = new_lines.pop()
            new_lines.append(prev.rstrip() + ' {% if user_review.rating|add:0 == i|add:0 %}checked{% endif %}>\n')
        else:
            new_lines.append(line)
    else:
        new_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

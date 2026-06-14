import os
import re

def process_file(source_path, dest_path):
    with open(source_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace src="public/image.png" with src="{{ url_for('static', filename='public/image.png') }}"
    content = re.sub(r'(src|href)=([\"\'\'])public/(.*?)([\"\'\'])', r"\1=\2{{ url_for('static', filename='public/\3') }}\4", content)

    # Some images might be referenced like src="image.png" without public/ if they were locally dumped. 
    # Let's also look for common images. The user said: "You place the images in the public folder, and then get the relative URLs"
    
    with open(dest_path, 'w', encoding='utf-8') as f:
        f.write(content)

process_file('itest-home.html', 'app/templates/landing/index.html')
process_file('student-dashboard.html', 'app/templates/dashboard/student.html')

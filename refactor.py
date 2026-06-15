import re
import os

html_content = open('app/templates/landing/index.html', encoding='utf-8').read()

# Extract CSS
style_match = re.search(r'<style>(.*?)</style>', html_content, re.DOTALL)
css = style_match.group(1) if style_match else ''
open('app/static/css/global.css', 'w', encoding='utf-8').write(css)

# Remove the old header I added if it's there
html_content = re.sub(r'<header class="top-header".*?</header>', '', html_content, flags=re.DOTALL)

# Extract footer
footer_match = re.search(r'(<section class="footer-subscribe">.*</div>\s*</div>)', html_content, re.DOTALL)
footer_html = footer_match.group(1) if footer_match else ''

# Create base.html
base_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{% block title %}}Exam Platform{{% endblock %}}</title>
    <link rel="stylesheet" href="{{{{ url_for('static', filename='css/global.css') }}}}">
    <style>
        /* Floating Main Header */
        .main-floating-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.5rem;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 1rem;
            padding: 0.75rem 1.5rem;
            box-shadow: 0 0.25rem 1.875rem rgba(0,0,0,0.08);
            width: calc(100% - 2.5rem);
            max-width: 68.75rem;
            margin: 1.25rem auto;
            position: sticky;
            top: 1.25rem;
            z-index: 1000;
        }}
        .header-logo {{
            font-weight: 800;
            font-size: 1.5rem;
            color: var(--text-heading);
            display: flex;
            align-items: center;
            gap: 0.5rem;
            text-decoration: none;
        }}
        .header-logo i {{
            color: var(--primary);
        }}
    </style>
    <script src="https://unpkg.com/lucide@latest"></script>
    {{% block head %}}{{% endblock %}}
</head>
<body>
    <header class="main-floating-header">
        <a href="/" class="header-logo">
            <i data-lucide="brain-circuit"></i>
            ExamZen
        </a>
        <div style="display: flex; align-items: center; gap: 1rem;">
            {{% if session.get('access_token') %}}
                <a href="{{{{ url_for('dashboard.index') }}}}" class="btn" style="background: var(--surface-2); color: var(--text-heading); border: 1px solid var(--border); padding: 0.5rem 1rem; border-radius: 0.5rem; text-decoration: none; font-weight: 600;">Dashboard</a>
                <div style="position: relative; display: inline-block;">
                    <button id="profileDropdownBtn" style="background: transparent; border: 1px solid var(--border); border-radius: 2rem; padding: 0.5rem 1rem; display: flex; align-items: center; gap: 0.75rem; cursor: pointer; font-weight: 600; color: var(--text-heading); transition: all 0.2s;">
                        {{% if session.get('user_info', {{}}).get('avatar_url') %}}
                            <img src="{{{{ session['user_info']['avatar_url'] }}}}" style="width: 24px; height: 24px; border-radius: 50%; object-fit: cover;">
                        {{% else %}}
                            <div style="width: 24px; height: 24px; border-radius: 50%; background: var(--primary); color: white; display: flex; align-items: center; justify-content: center; font-size: 0.75rem;">
                                {{{{ session.get('user_info', {{}}).get('name', 'U')[0] | upper }}}}
                            </div>
                        {{% endif %}}
                        {{{{ session.get('user_info', {{}}).get('name', 'User').split(' ')[0] }}}}
                        <i data-lucide="chevron-down" style="width: 16px; height: 16px;"></i>
                    </button>
                    <div id="profileDropdown" style="display: none; position: absolute; right: 0; top: 120%; background: white; border: 1px solid var(--border); border-radius: 0.75rem; min-width: 150px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); overflow: hidden;">
                        <a href="{{{{ url_for('auth.logout') }}}}" style="display: block; padding: 0.75rem 1rem; color: var(--red); text-decoration: none; font-size: 0.875rem;">Log Out</a>
                    </div>
                </div>
            {{% else %}}
                <a href="{{{{ url_for('auth.login') }}}}" style="color: var(--text-heading); text-decoration: none; font-weight: 600;">Log In</a>
                <a href="{{{{ url_for('auth.login') }}}}" style="background: var(--primary); color: white; padding: 0.6rem 1.25rem; border-radius: 0.5rem; text-decoration: none; font-weight: 600;">Sign Up</a>
            {{% endif %}}
        </div>
    </header>

    {{% block content %}}{{% endblock %}}

{footer_html}

    <script>
        lucide.createIcons();
        const profileBtn = document.getElementById('profileDropdownBtn');
        const profileDropdown = document.getElementById('profileDropdown');
        if (profileBtn && profileDropdown) {{
            profileBtn.addEventListener('click', (e) => {{
                e.stopPropagation();
                profileDropdown.style.display = profileDropdown.style.display === 'none' ? 'block' : 'none';
            }});
            document.addEventListener('click', () => {{
                profileDropdown.style.display = 'none';
            }});
        }}
    </script>
    {{% block extra_js %}}{{% endblock %}}
</body>
</html>'''

open('app/templates/base.html', 'w', encoding='utf-8').write(base_html)

# Create raw_base.html
raw_base_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Exam Platform{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/global.css') }}">
    {% block head %}{% endblock %}
</head>
<body>
    {% block content %}{% endblock %}
    {% block extra_js %}{% endblock %}
</body>
</html>'''
open('app/templates/raw_base.html', 'w', encoding='utf-8').write(raw_base_html)

# Extract the content from <section class="hero" id="hero"> down to just before <section class="footer-subscribe">
body_content = re.search(r'(<section class="hero" id="hero">.*?</section>\s*<section class="zenith-section".*?</section>)', html_content, re.DOTALL)
if body_content:
    content = body_content.group(1)
    
    script_match = re.search(r'(<script>\s*const nav = document.getElementById.*?)</script>', html_content, re.DOTALL)
    extra_js = script_match.group(1) + '</script>' if script_match else ''
    
    new_landing = f'''{{% extends "base.html" %}}

{{% block content %}}
{content}
{{% endblock %}}

{{% block extra_js %}}
{extra_js}
{{% endblock %}}
'''
    open('app/templates/landing/index.html', 'w', encoding='utf-8').write(new_landing)

print('Refactoring complete')

from flask import Flask, request, render_template, send_file, flash, redirect, url_for
import os
import zipfile
import subprocess
import tempfile
import shutil
import re
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'change-me')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
ALLOWED_EXTENSIONS = {'zip', 'tex', 'latex'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def tikz_tools_available():
    return shutil.which('pdflatex') is not None and shutil.which('pdftoppm') is not None

def has_tikz(content):
    return bool(re.search(r'\\begin\{tikzpicture\}', content))

def extract_title_info(content):
    title_match = re.search(r'\\title\{([^}]*)\}', content)
    author_match = re.search(r'\\author\{([^}]*)\}', content)
    date_match = re.search(r'\\date\{([^}]*)\}', content)

    title = title_match.group(1).strip() if title_match else ''
    author = author_match.group(1).strip() if author_match else ''
    date = date_match.group(1).strip() if date_match else ''
    return title, author, date

def build_title_block(title, author, date):
    if not title and not author and not date:
        return None

    lines = [r'\begin{center}']
    if title:
        lines.append(r'{\LARGE ' + title + r'\par}')
    if author:
        lines.append(r'\vspace{0.5em}')
        lines.append(r'{\large ' + author + r'\par}')
    if date:
        lines.append(r'\vspace{0.5em}')
        lines.append(r'{\large ' + date + r'\par}')
    lines.append(r'\end{center}')
    return '\n'.join(lines)

def preprocess_latex(latex_content):
    """Simple but effective LaTeX preprocessing for theorem environments"""

    # Theorem environment mappings
    theorem_envs = {
        'definition': 'Definition',
        'theorem': 'Theorem',
        'lemma': 'Lemma',
        'corollary': 'Corollary',
        'proposition': 'Proposition',
        'remark': 'Remark',
        'example': 'Example',
        'exercise': 'Exercise',
        'proof': 'Proof'
    }

    title, author, date = extract_title_info(latex_content)
    title_block = build_title_block(title, author, date)

    def convert_framebox_parbox(text):
        pattern = re.compile(
            r'\\framebox\{\\parbox\{[^}]*\}\{([\s\S]*?)\}\}',
            re.MULTILINE
        )
        return pattern.sub(r'\\begin{quote}\n\1\n\\end{quote}', text)

    def split_comment(line):
        match = re.search(r'(?<!\\)%', line)
        if match:
            return line[:match.start()], line[match.start():]
        return line, ''

    latex_content = convert_framebox_parbox(latex_content)

    if title_block:
        if r'\maketitle' in latex_content:
            latex_content = latex_content.replace(r'\maketitle', title_block)
        elif r'\begin{document}' in latex_content:
            latex_content = latex_content.replace(r'\begin{document}', r'\begin{document}' + '\n' + title_block, 1)
        else:
            latex_content = title_block + '\n' + latex_content

    # Process theorem environments with blockquote wrappers, skipping comments
    lines = latex_content.split('\n')
    updated_lines = []
    for line in lines:
        code, comment = split_comment(line)
        code = re.sub(r'\\begin\{multicols\}\{[^}]+\}', '', code)
        code = re.sub(r'\\end\{multicols\}', '', code)
        for env_name, display_name in theorem_envs.items():
            begin_pattern = rf'\\begin\{{{env_name}\}}(?:\[(?P<title>[^\]]+)\])?'
            end_pattern = rf'\\end\{{{env_name}\}}'

            def replace_begin(match):
                title = match.group('title')
                title_suffix = f" ({title})" if title else ""
                return f'\\begin{{quote}}\n\\textbf{{{display_name}{title_suffix}:}} '

            code = re.sub(begin_pattern, replace_begin, code)
            code = re.sub(end_pattern, r'\\end{quote}', code)
        updated_lines.append(code + comment)
    latex_content = '\n'.join(updated_lines)

    # Handle labels and references
    latex_content = re.sub(r'\\label\{([^}]+)\}', r'', latex_content)  # Remove labels
    latex_content = re.sub(r'\\ref\{([^}]+)\}', r'\\textit{\1}', latex_content)  # Convert refs to italic

    return latex_content

def preprocess_tikz(latex_content, work_dir, output_dir):
    """Render TikZ pictures to PNG and replace them with includegraphics."""
    if not tikz_tools_available():
        print("Warning: TikZ detected but pdflatex or pdftoppm is not installed; skipping TikZ blocks.")
        return latex_content, []

    if r'\usepackage{graphicx}' not in latex_content:
        if r'\documentclass' in latex_content:
            latex_content = re.sub(
                r'(\\documentclass[^\n]*\n)',
                r'\1\\usepackage{graphicx}\n',
                latex_content,
                count=1
            )
        else:
            latex_content = '\\usepackage{graphicx}\n' + latex_content

    tikz_pattern = re.compile(
        r'\\begin\{tikzpicture\}[\s\S]*?\\end\{tikzpicture\}',
        re.MULTILINE
    )
    matches = list(tikz_pattern.finditer(latex_content))
    if not matches:
        return latex_content, []

    png_paths = []
    new_parts = []
    last_idx = 0

    with tempfile.TemporaryDirectory(dir=work_dir) as temp_dir:
        for idx, match in enumerate(matches, start=1):
            tikz_block = match.group(0)
            tex_name = f"tikz_{idx}.tex"
            pdf_name = f"tikz_{idx}.pdf"
            png_base = f"tikz_{idx}"
            png_name = f"{png_base}.png"
            tex_path = os.path.join(temp_dir, tex_name)

            tex_content = (
                "\\documentclass[tikz]{standalone}\n"
                "\\usepackage{tikz}\n"
                "\\begin{document}\n"
                f"{tikz_block}\n"
                "\\end{document}\n"
            )
            with open(tex_path, 'w', encoding='utf-8') as f:
                f.write(tex_content)

            pdflatex_cmd = [
                'pdflatex',
                '-interaction=nonstopmode',
                '-halt-on-error',
                '-output-directory', temp_dir,
                tex_path
            ]
            result = subprocess.run(pdflatex_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Warning: TikZ render failed for block {idx}: {result.stderr}")
                continue

            pdf_path = os.path.join(temp_dir, pdf_name)
            ppm_cmd = [
                'pdftoppm',
                '-png',
                '-singlefile',
                pdf_path,
                os.path.join(temp_dir, png_base)
            ]
            result = subprocess.run(ppm_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Warning: pdftoppm failed for block {idx}: {result.stderr}")
                continue

            png_path = os.path.join(temp_dir, png_name)
            final_png = os.path.join(work_dir, png_name)
            shutil.copy2(png_path, final_png)
            png_paths.append(final_png)

            new_parts.append(latex_content[last_idx:match.start()])
            new_parts.append(f"\\begin{{center}}\\includegraphics{{{png_name}}}\\end{{center}}")
            last_idx = match.end()

        new_parts.append(latex_content[last_idx:])

    return ''.join(new_parts), png_paths

def preprocess_beamer_frames(latex_content):
    """Convert beamer frames to section headings for reveal.js output"""
    def split_comment(line):
        match = re.search(r'(?<!\\)%', line)
        if match:
            return line[:match.start()], line[match.start():]
        return line, ''

    inside_frame = False
    frame_title_set = False
    output_lines = []

    for line in latex_content.split('\n'):
        code, comment = split_comment(line)

        begin_match = re.search(r'\\begin\{frame\}(?:\[[^\]]*\])?(?:\{([^}]*)\})?', code)
        if begin_match:
            inside_frame = True
            frame_title_set = False
            title = begin_match.group(1) or ''
            if title.strip():
                output_lines.append(f'\\section{{{title.strip()}}}')
                frame_title_set = True
            code = re.sub(r'\\begin\{frame\}(?:\[[^\]]*\])?(?:\{[^}]*\})?', '', code)

        if inside_frame:
            title_match = re.search(r'\\frametitle\{([^}]*)\}', code)
            if title_match:
                title = title_match.group(1).strip()
                if title and not frame_title_set:
                    output_lines.append(f'\\section{{{title}}}')
                    frame_title_set = True
                code = re.sub(r'\\frametitle\{[^}]*\}', '', code)

        if r'\end{frame}' in code:
            code = code.replace(r'\end{frame}', '')
            inside_frame = False
            frame_title_set = False

        output_lines.append((code + comment).strip())

    return '\n'.join([line for line in output_lines if line])

def resolve_includes(latex_content, base_dir):
    """Resolve \\include and \\input commands"""
    lines = latex_content.split('\n')
    resolved_lines = []
    
    for line in lines:
        # Handle \\include{filename} and \\input{filename}
        include_match = re.search(r'\\(?:include|input)\{([^}]+)\}', line)
        if include_match:
            filename = include_match.group(1)
            if not filename.endswith('.tex'):
                filename += '.tex'
            
            include_path = os.path.join(base_dir, filename)
            # Try with .tex extension if file doesn't exist
            if not os.path.exists(include_path) and not filename.endswith('.tex'):
                include_path = os.path.join(base_dir, filename + '.tex')
            
            if os.path.exists(include_path):
                with open(include_path, 'r', encoding='utf-8', errors='ignore') as f:
                    included_content = f.read()
                # Recursively resolve includes in the included file
                included_content = resolve_includes(included_content, os.path.dirname(include_path))
                resolved_lines.append(included_content)
            else:
                print(f"Warning: Could not find include file: {filename}")
                resolved_lines.append(line)  # Keep original if file not found
        else:
            resolved_lines.append(line)
    
    return '\n'.join(resolved_lines)

def create_quarto_website(latex_file_path, output_dir):
    """Create Quarto website with sidebar navigation based on chapters/sections"""
    work_dir = os.path.dirname(latex_file_path)
    
    # Read and resolve all includes first
    with open(latex_file_path, 'r', encoding='utf-8', errors='ignore') as f:
        latex_content = f.read()
    
    resolved_content = resolve_includes(latex_content, work_dir)
    resolved_content, tikz_imgs = preprocess_tikz(resolved_content, work_dir, output_dir)
    processed_content = preprocess_latex(resolved_content)
    title, _, _ = extract_title_info(resolved_content)
    site_title = title if title else "LaTeX Document"
    
    # Create _quarto.yml without left sidebar
    quarto_config = f"""project:
  type: website

website:
  title: "{site_title}"

format:
  html:
    theme: cosmo
    css: styles.css
    toc: true
    toc-location: right
    number-sections: true
    number-depth: 3
"""
    
    with open(os.path.join(work_dir, '_quarto.yml'), 'w') as f:
        f.write(quarto_config)

    styles_css = """
/* Wider content with extra spacing before TOC */
.page-columns { column-gap: 3rem; }
.content { max-width: 1200px; margin-left: 2vw; }
nav#TOC { margin-left: 1rem; }
"""
    with open(os.path.join(work_dir, 'styles.css'), 'w', encoding='utf-8') as f:
        f.write(styles_css)
    
    # Convert LaTeX to markdown using pandoc
    temp_tex = os.path.join(work_dir, 'temp_full.tex')
    temp_md = os.path.join(work_dir, 'temp_content.md')
    
    with open(temp_tex, 'w', encoding='utf-8') as f:
        f.write(processed_content)
    
    # Use pandoc to convert LaTeX to markdown
    pandoc_cmd = [
        'pandoc', 'temp_full.tex',
        '--from=latex+raw_tex',
        '--to=markdown',
        '--output=temp_content.md'
    ]
    
    subprocess.run(pandoc_cmd, cwd=work_dir, capture_output=True, check=True)
    
    # Read converted markdown
    with open(temp_md, 'r', encoding='utf-8') as f:
        markdown_content = f.read()
    
    # Create index.qmd with converted content
    with open(os.path.join(work_dir, 'index.qmd'), 'w') as f:
        f.write(f'---\ntitle: "{site_title}"\n---\n\n{markdown_content}')
    
    # Clean up temp files
    for temp_file in [temp_tex, temp_md]:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    # Render Quarto website
    try:
        subprocess.run(['quarto', 'render'], cwd=work_dir, capture_output=True, check=True)
        
        # Copy _site contents to output directory
        site_dir = os.path.join(work_dir, '_site')
        if not os.path.exists(site_dir):
            raise Exception("Quarto output directory was not created.")

        for item in os.listdir(site_dir):
            src = os.path.join(site_dir, item)
            dst = os.path.join(output_dir, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

        for img_path in tikz_imgs:
            img_name = os.path.basename(img_path)
            if not os.path.exists(os.path.join(output_dir, img_name)):
                shutil.copy2(img_path, os.path.join(output_dir, img_name))

        index_path = os.path.join(output_dir, 'index.html')
        base_name = os.path.splitext(os.path.basename(latex_file_path))[0]
        named_path = os.path.join(output_dir, f"{base_name}.html")
        if os.path.exists(index_path) and not os.path.exists(named_path):
            shutil.copy2(index_path, named_path)

        html_found = False
        for root, _, files in os.walk(output_dir):
            for filename in files:
                if filename.endswith('.html'):
                    html_found = True
                    enhance_html_accessibility(os.path.join(root, filename))
        if not html_found:
            raise Exception("No HTML files were generated by Quarto.")
        return True
    except subprocess.CalledProcessError as e:
        raise Exception(f"Quarto render failed: {e.stderr}")

def convert_latex_to_html(latex_file_path, output_path):
    """Convert LaTeX to HTML with enhanced error handling and theorem support"""
    work_dir = os.path.dirname(latex_file_path)
    output_dir = os.path.dirname(output_path)
    
    try:
        # Validate input file
        if not os.path.exists(latex_file_path):
            raise FileNotFoundError(f"LaTeX file not found: {latex_file_path}")
        
        with open(latex_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if not content.strip():
            raise ValueError("LaTeX file is empty")
        
        # Check for common LaTeX errors
        validation_errors = validate_latex_content(content)
        if validation_errors:
            print(f"Warning: LaTeX validation issues found: {'; '.join(validation_errors)}")
        
        def convert_with_pandoc(processed_content, output_format='html5'):
            temp_tex = os.path.join(work_dir, 'temp_processed.tex')
            with open(temp_tex, 'w', encoding='utf-8') as f:
                f.write(processed_content)

            pandoc_cmd = [
                'pandoc', temp_tex,
                '--from=latex',
                '--to=' + output_format,
                '--standalone',
                '--mathjax',
                '--resource-path=' + work_dir,
                '--output=' + output_path
            ]
            if output_format == 'revealjs':
                pandoc_cmd.extend([
                    '--variable', 'revealjs-url=https://unpkg.com/reveal.js@5'
                ])

            result = subprocess.run(pandoc_cmd, capture_output=True, text=True)

            if result.returncode != 0:
                error_msg = f"Pandoc conversion failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                raise Exception(error_msg)

            if os.path.exists(temp_tex):
                os.remove(temp_tex)

            if output_format != 'revealjs':
                enhance_html_accessibility(output_path)
            return True

        is_beamer = bool(re.search(r'\\documentclass(?:\[[^\]]*\])?\{beamer\}', content))

        if is_beamer:
            processed_content = preprocess_beamer_frames(content)
            processed_content = preprocess_latex(processed_content)
            return convert_with_pandoc(processed_content, output_format='revealjs')
        tikz_imgs = []
        if re.search(r'\\(?:include|input|chapter|section)\{[^}]+\}', content):
            try:
                return create_quarto_website(latex_file_path, output_dir)
            except Exception as e:
                print(f"Warning: Quarto render failed, falling back to single HTML: {e}")
                resolved_content = resolve_includes(content, work_dir)
                resolved_content, tikz_imgs = preprocess_tikz(resolved_content, work_dir, output_dir)
                if is_beamer:
                    processed_content = preprocess_beamer_frames(resolved_content)
                else:
                    processed_content = resolved_content
                processed_content = preprocess_latex(processed_content)
                output_format = 'revealjs' if is_beamer else 'html5'
                result = convert_with_pandoc(processed_content, output_format=output_format)
                for img_path in tikz_imgs:
                    img_name = os.path.basename(img_path)
                    shutil.copy2(img_path, os.path.join(output_dir, img_name))
                return result
        else:
            if is_beamer:
                processed_content = preprocess_beamer_frames(content)
            else:
                processed_content = content
            processed_content, tikz_imgs = preprocess_tikz(processed_content, work_dir, output_dir)
            processed_content = preprocess_latex(processed_content)
            output_format = 'revealjs' if is_beamer else 'html5'
            result = convert_with_pandoc(processed_content, output_format=output_format)
            for img_path in tikz_imgs:
                img_name = os.path.basename(img_path)
                shutil.copy2(img_path, os.path.join(output_dir, img_name))
            return result
            
    except FileNotFoundError as e:
        raise Exception(f"File error: {str(e)}")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Conversion process failed: {e.stderr.decode() if e.stderr else 'Unknown error'}")
    except Exception as e:
        raise Exception(f"Conversion error: {str(e)}")

def validate_latex_content(content):
    """Validate LaTeX content and return list of potential issues"""
    errors = []
    
    # Check for unmatched braces
    open_braces = content.count('{')
    close_braces = content.count('}')
    if open_braces != close_braces:
        errors.append(f"Unmatched braces: {open_braces} open, {close_braces} close")
    
    # Check for common undefined commands
    undefined_commands = []
    common_commands = ['textbf', 'textit', 'emph', 'section', 'subsection', 'chapter', 'title', 'author', 'date', 'today', 'maketitle', 'ref', 'label']
    for match in re.finditer(r'\\([a-zA-Z]+)', content):
        cmd = match.group(1)
        if cmd not in common_commands and len(cmd) > 2:
            if cmd not in ['begin', 'end', 'documentclass', 'usepackage']:
                undefined_commands.append(cmd)
    
    if undefined_commands:
        unique_cmds = list(set(undefined_commands))[:5]  # Limit to 5
        errors.append(f"Potentially undefined commands: {', '.join(unique_cmds)}")
    
    # Check for missing document structure
    if '\\documentclass' not in content and '\\begin{document}' not in content:
        errors.append("Missing document structure (\\documentclass or \\begin{document})")
    
    return errors

def enhance_html_accessibility(html_path):
    """Add accessibility enhancements and theorem styling to HTML"""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Add data attributes to theorem paragraphs for better styling
        theorem_keywords = ['Definition:', 'Theorem:', 'Lemma:', 'Corollary:', 'Proposition:', 'Remark:', 'Example:', 'Exercise:', 'Proof:']
        for keyword in theorem_keywords:
            env_name = keyword.lower().replace(':', '')
            # Add data attribute to paragraphs containing theorem keywords
            pattern = f'<p><strong>{keyword}</strong>'
            replacement = f'<p data-theorem="{env_name}"><strong>{keyword}</strong>'
            content = content.replace(pattern, replacement)
            # Also handle cases where strong tags are at the beginning of paragraphs
            pattern2 = f'<strong>{keyword}</strong>'
            replacement2 = f'<strong class="theorem-label">{keyword}</strong>'
            content = content.replace(pattern2, replacement2)
            # Add theorem classes to blockquotes
            blockquote_pattern = re.compile(rf'<blockquote>(\s*<p>\s*<strong>{re.escape(keyword)}</strong>)')
            content = blockquote_pattern.sub(
                rf'<blockquote class="theorem-block" data-theorem="{env_name}">\1',
                content
            )
        
        # Enhanced accessibility CSS with theorem support
        accessibility_css = """
<style>
/* Accessibility enhancements */
body { font-family: Arial, sans-serif; line-height: 1.6; max-width: 1200px; margin: 0 6vw 0 2vw; padding: 20px; }
h1, h2, h3, h4, h5, h6 { margin-top: 1.5em; margin-bottom: 0.5em; }
p { margin-bottom: 1em; }
img { max-width: 100%; height: auto; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
th { background-color: #f2f2f2; font-weight: bold; }
a { color: #0066cc; text-decoration: underline; }
a:hover, a:focus { background-color: #f0f8ff; }
.math { font-family: 'Times New Roman', serif; }
@media (prefers-reduced-motion: reduce) { * { animation-duration: 0.01ms !important; } }

/* Enhanced theorem styling */
body { font-family: 'Times New Roman', serif; }

/* Theorem labels - make them bold and colored */
.theorem-label,
strong.theorem-label {
    color: #007acc !important;
    font-size: 1.1em !important;
    font-weight: bold !important;
}

/* Style paragraphs with theorem data attributes */
p[data-theorem] {
    margin: 1.5em 0;
    padding: 1em;
    border-left: 4px solid #007acc;
    background-color: #f8f9fa;
    border-radius: 4px;
}

/* Theorem blockquotes */
.theorem-block {
    margin: 1.5em 0;
    padding: 1em;
    border-left: 4px solid #007acc;
    background-color: #f8f9fa;
    border-radius: 4px;
}

.theorem-block > p:first-child {
    margin-top: 0;
}

.theorem-block > p:last-child {
    margin-bottom: 0;
}

/* Framebox-like quotes */
blockquote:not(.theorem-block) {
    margin: 1.2em 0;
    padding: 1em;
    border: 1px solid #ddd;
    background-color: #f8f9fa;
    border-radius: 4px;
}

/* Specific styling based on content */
p[data-theorem="definition"],
.theorem-block[data-theorem="definition"] {
    border-left-color: #dc3545;
    background-color: #fff8f8;
}

p[data-theorem="theorem"],
p[data-theorem="lemma"],
p[data-theorem="corollary"],
p[data-theorem="proposition"],
.theorem-block[data-theorem="theorem"],
.theorem-block[data-theorem="lemma"],
.theorem-block[data-theorem="corollary"],
.theorem-block[data-theorem="proposition"] {
    border-left-color: #28a745;
    background-color: #f8fff8;
}

p[data-theorem="example"],
p[data-theorem="exercise"],
.theorem-block[data-theorem="example"],
.theorem-block[data-theorem="exercise"] {
    border-left-color: #ffc107;
    background-color: #fffdf0;
}

p[data-theorem="proof"],
.theorem-block[data-theorem="proof"] {
    border-left-color: #6c757d;
    background-color: #f1f3f4;
}
</style>
"""
        
        # Insert CSS before closing head tag
        if '</head>' in content:
            content = content.replace('</head>', accessibility_css + '</head>')
        else:
            # If no head tag, add it
            content = '<head>' + accessibility_css + '</head>' + content
        
        # Add lang attribute if missing
        content = re.sub(r'<html(?![^>]*\blang=)([^>]*)>', r'<html\1 lang="en">', content, count=1)
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
    except Exception as e:
        print(f"Warning: Could not enhance HTML accessibility: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        if not tikz_tools_available():
            try:
                if filename.lower().endswith('.zip'):
                    with zipfile.ZipFile(filepath, 'r') as zip_ref:
                        for member in zip_ref.namelist():
                            if member.lower().endswith(('.tex', '.latex')):
                                content = zip_ref.read(member).decode('utf-8', errors='ignore')
                                if has_tikz(content):
                                    flash('TikZ detected but pdflatex/pdftoppm not installed; TikZ graphics will be skipped.', 'warning')
                                    break
                else:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    if has_tikz(content):
                        flash('TikZ detected but pdflatex/pdftoppm not installed; TikZ graphics will be skipped.', 'warning')
            except Exception:
                pass
        
        try:
            if filename.lower().endswith('.zip'):
                # Process ZIP file
                output_dir = process_latex_zip(filepath)
            else:
                # Process single LaTeX file
                output_dir = process_single_latex_file(filepath)
            return render_template('success.html', output_dir=output_dir)
        except Exception as e:
            flash(f'Error processing file: {str(e)}', 'error')
            return redirect(url_for('index'))
    
    flash('Invalid file type. Please upload a ZIP, TEX, or LATEX file.', 'error')
    return redirect(url_for('index'))

def process_latex_zip(zip_path):
    """Extract and convert LaTeX files from zip"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract zip
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find LaTeX files - prioritize main.tex
        latex_files = []
        main_tex = None
        
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.endswith(('.tex', '.latex')) and not file.startswith('.'):
                    full_path = os.path.join(root, file)
                    if file.lower() == 'main.tex':
                        main_tex = full_path
                    else:
                        latex_files.append(full_path)
        
        # If main.tex exists, only process that
        if main_tex:
            latex_files = [main_tex]
        
        if not latex_files:
            raise Exception("No LaTeX files found in the zip archive")
        
        # Create output directory
        output_name = os.path.splitext(os.path.basename(zip_path))[0]
        output_dir = os.path.join(OUTPUT_FOLDER, output_name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Convert each LaTeX file
        successes = 0
        errors = []
        for latex_file in latex_files:
            base_name = os.path.splitext(os.path.basename(latex_file))[0]
            html_path = os.path.join(output_dir, f"{base_name}.html")
            
            try:
                convert_latex_to_html(latex_file, html_path)
                if os.path.exists(html_path):
                    print(f"Successfully converted: {base_name}.html")
                    successes += 1
                else:
                    message = f"{base_name}.html was not created at {html_path}"
                    print(f"Warning: {message}")
                    errors.append(message)
            except Exception as e:
                message = f"Error converting {latex_file}: {e}"
                print(message)
                errors.append(message)
                continue

        if successes == 0:
            detail = "; ".join(errors[:3])
            raise Exception(f"No files were converted successfully. {detail}")
        
        return output_name

def process_single_latex_file(latex_path):
    """Process a single LaTeX file"""
    try:
        # Get absolute path
        abs_latex_path = os.path.abspath(latex_path)
        
        # Validate file exists and is readable
        if not os.path.exists(abs_latex_path):
            raise FileNotFoundError(f"File not found: {abs_latex_path}")
        
        # Create output directory
        base_name = os.path.splitext(os.path.basename(abs_latex_path))[0]
        output_dir = os.path.join(OUTPUT_FOLDER, base_name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Convert LaTeX to HTML
        html_path = os.path.join(output_dir, f"{base_name}.html")
        
        try:
            convert_latex_to_html(abs_latex_path, html_path)
            if os.path.exists(html_path):
                enhance_html_accessibility(html_path)
                print(f"Successfully converted: {base_name}.html")
            else:
                raise Exception(f"HTML file was not created at {html_path}")
        except Exception as e:
            raise Exception(f"Error converting {abs_latex_path}: {str(e)}")
        
        return base_name
        
    except Exception as e:
        raise Exception(f"Failed to process LaTeX file: {str(e)}")

@app.route('/download/<path:filename>')
def download_file(filename):
    # Create a zip file of the output directory
    output_dir = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(output_dir):
        zip_path = f"{output_dir}.zip"
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, output_dir)
                    zipf.write(file_path, arcname)
        return send_file(zip_path, as_attachment=True)
    else:
        flash('Output files not found')
        return redirect(url_for('index'))

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    port = int(os.environ.get('PORT', '8000'))
    app.run(debug=debug, host='0.0.0.0', port=port)

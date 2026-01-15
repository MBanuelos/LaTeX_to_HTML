#!/usr/bin/env python3
"""
Simple LaTeX to HTML converter with enhanced theorem support and error handling
"""

import re
import os
import subprocess
import tempfile

def preprocess_latex_simple(content):
    """Simple but effective LaTeX preprocessing"""
    
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
    
    # Process theorem environments
    for env_name, display_name in theorem_envs.items():
        # Replace begin/end with custom markup that pandoc will preserve
        begin_pattern = rf'\\begin\{{{env_name}\}}'
        end_pattern = rf'\\end\{{{env_name}\}}'
        
        # Handle labels
        def replace_begin(match):
            return f'\\textbf{{{display_name}:}} '
        
        content = re.sub(begin_pattern, replace_begin, content)
        content = re.sub(end_pattern, '', content)
    
    # Handle labels and references better
    content = re.sub(r'\\label\{([^}]+)\}', r'', content)  # Remove labels for now
    content = re.sub(r'\\ref\{([^}]+)\}', r'\\textit{\\1}', content)  # Convert refs to italic
    
    return content

def convert_latex_simple(input_file, output_file):
    """Convert LaTeX to HTML with preprocessing"""
    
    try:
        # Read input file
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Preprocess
        processed_content = preprocess_latex_simple(content)
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tex', delete=False) as temp_file:
            temp_file.write(processed_content)
            temp_path = temp_file.name
        
        try:
            # Convert with pandoc
            cmd = [
                'pandoc', temp_path,
                '--from=latex',
                '--to=html5',
                '--standalone',
                '--mathjax',
                '--output=' + output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Pandoc failed: {result.stderr}")
            
            # Post-process HTML for better theorem styling
            post_process_html(output_file)
            
            return True
            
        finally:
            # Clean up temp file
            os.unlink(temp_path)
            
    except Exception as e:
        raise Exception(f"Conversion failed: {str(e)}")

def post_process_html(html_file):
    """Add enhanced styling to the HTML output"""
    
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add custom CSS for theorem-like environments
    custom_css = """
<style>
/* Enhanced theorem styling */
body { 
    font-family: 'Times New Roman', serif; 
    line-height: 1.6; 
    max-width: 800px; 
    margin: 0 auto; 
    padding: 20px; 
}

/* Theorem-like environments */
p:has(strong:contains("Definition:")),
p:has(strong:contains("Theorem:")),
p:has(strong:contains("Lemma:")),
p:has(strong:contains("Corollary:")),
p:has(strong:contains("Proposition:")),
p:has(strong:contains("Remark:")),
p:has(strong:contains("Example:")),
p:has(strong:contains("Exercise:")),
p:has(strong:contains("Proof:")) {
    margin: 1.5em 0;
    padding: 1em;
    border-left: 4px solid #007acc;
    background-color: #f8f9fa;
    border-radius: 4px;
}

/* Specific colors for different types */
p:has(strong:contains("Definition:")) {
    border-left-color: #dc3545;
    background-color: #fff8f8;
}

p:has(strong:contains("Theorem:")),
p:has(strong:contains("Lemma:")),
p:has(strong:contains("Corollary:")),
p:has(strong:contains("Proposition:")) {
    border-left-color: #28a745;
    background-color: #f8fff8;
}

p:has(strong:contains("Example:")),
p:has(strong:contains("Exercise:")) {
    border-left-color: #ffc107;
    background-color: #fffdf0;
}

p:has(strong:contains("Proof:")) {
    border-left-color: #6c757d;
    background-color: #f1f3f4;
}

/* Math styling */
.math { font-family: 'Times New Roman', serif; }

/* Accessibility */
@media (prefers-reduced-motion: reduce) { 
    * { animation-duration: 0.01ms !important; } 
}
</style>
"""
    
    # Insert CSS before closing head tag
    if '</head>' in content:
        content = content.replace('</head>', custom_css + '</head>')
    
    # Add lang attribute if missing
    if 'lang=' not in content:
        content = content.replace('<html', '<html lang="en"')
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python simple_converter.py input.tex output.html")
        sys.exit(1)
    
    try:
        convert_latex_simple(sys.argv[1], sys.argv[2])
        print(f"Successfully converted {sys.argv[1]} to {sys.argv[2]}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
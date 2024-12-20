from difflib import SequenceMatcher
import re
import html

def compare_texts(text1, text2, mode='side-by-side'):
    """
    Compare two texts while preserving all formatting including newlines.
    Returns either a tuple of highlighted texts (side-by-side) or single merged text (inline).
    """
    def escape_html(text):
        return html.escape(text).replace(' ', '&nbsp;')
    
    # Split texts into lines while preserving empty lines
    lines1 = text1.splitlines(keepends=True)
    lines2 = text2.splitlines(keepends=True)
    
    matcher = SequenceMatcher(None, lines1, lines2)
    result1 = []
    result2 = []
    
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            # Add unchanged lines without wrapping spans for equal content
            for line in lines1[i1:i2]:
                result1.append(escape_html(line))
                result2.append(escape_html(line))
        elif op == 'delete':
            # Add deleted lines (only in text1)
            for line in lines1[i1:i2]:
                result1.append(f'<span class="bg-red-100 text-red-800">{escape_html(line)}</span>')
        elif op == 'insert':
            # Add inserted lines (only in text2)
            for line in lines2[j1:j2]:
                result2.append(f'<span class="bg-green-100 text-green-800">{escape_html(line)}</span>')
        elif op == 'replace':
            # Add modified lines
            for line in lines1[i1:i2]:
                result1.append(f'<span class="bg-red-100 text-red-800">{escape_html(line)}</span>')
            for line in lines2[j1:j2]:
                result2.append(f'<span class="bg-green-100 text-green-800">{escape_html(line)}</span>')
    
    if mode == 'side-by-side':
        return ''.join(result1), ''.join(result2)
    else:
        # For inline view, merge the results intelligently
        inline_result = []
        i = j = 0
        while i < len(result1) or j < len(result2):
            if i < len(result1) and (j >= len(result2) or result1[i] == result2[j]):
                inline_result.append(result1[i])
                i += 1
                j += 1
            else:
                if i < len(result1) and '<span class="bg-red-100' in result1[i]:
                    inline_result.append(result1[i])
                    i += 1
                if j < len(result2) and '<span class="bg-green-100' in result2[j]:
                    inline_result.append(result2[j])
                    j += 1
        
        return ''.join(inline_result)
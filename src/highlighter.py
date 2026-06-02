import os
from gi.repository import Pango

# Optional tree-sitter package
try:
    import tree_sitter
    import tree_sitter_languages
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False


class TreeSitterHighlighter:
    """Uses tree-sitter to perform precise AST-based semantic highlighting when available."""
    def __init__(self, buffer, filepath, is_dark=True):
        self.buffer = buffer
        self.filepath = filepath
        self.parser = None
        self.lang = None
        self.tags = {}
        self.is_dark = is_dark
        
        if not HAS_TREE_SITTER or not filepath:
            return
            
        ext = os.path.splitext(filepath)[1].lower()
        lang_id = None
        if ext == '.rs':
            lang_id = 'rust'
        elif ext == '.py':
            lang_id = 'python'
        elif ext in ['.c', '.cpp', '.h', '.cc']:
            lang_id = 'c'
            
        if lang_id:
            try:
                self.lang = tree_sitter_languages.get_language(lang_id)
                self.parser = tree_sitter.Parser()
                self.parser.set_language(self.lang)
                
                # Define highlight tags
                colors = {
                    'keyword': ("#cba6f7", "#8839ef"),
                    'string': ("#a6e3a1", "#40a02b"),
                    'comment': ("#585b70", "#9ca0b0"),
                    'function': ("#89b4fa", "#1e66f5"),
                    'type': ("#f9e2af", "#df8e1d"),
                    'number': ("#fab387", "#fe640b"),
                }
                
                self.tags = {
                    'keyword': buffer.create_tag("ts_keyword", foreground=colors['keyword'][0] if is_dark else colors['keyword'][1], weight=Pango.Weight.BOLD),
                    'string': buffer.create_tag("ts_string", foreground=colors['string'][0] if is_dark else colors['string'][1]),
                    'comment': buffer.create_tag("ts_comment", foreground=colors['comment'][0] if is_dark else colors['comment'][1], style=Pango.Style.ITALIC),
                    'function': buffer.create_tag("ts_function", foreground=colors['function'][0] if is_dark else colors['function'][1]),
                    'type': buffer.create_tag("ts_type", foreground=colors['type'][0] if is_dark else colors['type'][1]),
                    'number': buffer.create_tag("ts_number", foreground=colors['number'][0] if is_dark else colors['number'][1]),
                }
            except Exception as e:
                print(f"[TreeSitter] Initialization failed for {filepath}: {e}")

    def update_theme(self, is_dark):
        self.is_dark = is_dark
        if not self.tags:
            return
        colors = {
            'keyword': ("#cba6f7", "#8839ef"),
            'string': ("#a6e3a1", "#40a02b"),
            'comment': ("#585b70", "#9ca0b0"),
            'function': ("#89b4fa", "#1e66f5"),
            'type': ("#f9e2af", "#df8e1d"),
            'number': ("#fab387", "#fe640b"),
        }
        for key, (dark_color, light_color) in colors.items():
            if key in self.tags:
                self.tags[key].set_property("foreground", dark_color if is_dark else light_color)

    def highlight(self):
        if not self.parser:
            return
            
        start = self.buffer.get_start_iter()
        end = self.buffer.get_end_iter()
        text = self.buffer.get_text(start, end, True)
        
        try:
            tree = self.parser.parse(text.encode('utf-8'))
            
            # Clear previous highlights
            for tag in self.tags.values():
                self.buffer.remove_tag(tag, start, end)
                
            self._apply_highlight_node(tree.root_node, text)
        except Exception as e:
            print(f"[TreeSitter] Highlighting error: {e}")

    def _apply_highlight_node(self, node, full_text):
        node_type = node.type
        tag_key = None
        
        if node_type in ['keyword', 'conditional', 'repeat', 'return_statement', 'let_keyword']:
            tag_key = 'keyword'
        elif node_type in ['string', 'raw_string_literal', 'char_literal']:
            tag_key = 'string'
        elif node_type in ['comment', 'line_comment', 'block_comment']:
            tag_key = 'comment'
        elif node_type in ['function_definition', 'call_expression', 'function_item']:
            tag_key = 'function'
        elif node_type in ['type_identifier', 'primitive_type']:
            tag_key = 'type'
        elif node_type in ['number_literal', 'integer_literal', 'float_literal']:
            tag_key = 'number'
            
        if tag_key and tag_key in self.tags:
            s_byte = node.start_byte
            e_byte = node.end_byte
            
            # Convert byte offset to character offset
            s_char = len(full_text.encode('utf-8')[:s_byte].decode('utf-8', errors='ignore'))
            e_char = len(full_text.encode('utf-8')[:e_byte].decode('utf-8', errors='ignore'))
            
            s_iter = self.buffer.get_iter_at_offset(s_char)
            e_iter = self.buffer.get_iter_at_offset(e_char)
            self.buffer.apply_tag(self.tags[tag_key], s_iter, e_iter)
            
        for child in node.children:
            self._apply_highlight_node(child, full_text)

    def get_indent_depth_at_char_offset(self, char_offset):
        if not self.parser or not self.lang:
            return 0
            
        start = self.buffer.get_start_iter()
        end = self.buffer.get_end_iter()
        text = self.buffer.get_text(start, end, True)
        
        try:
            tree = self.parser.parse(text.encode('utf-8'))
            byte_offset = len(text[:char_offset].encode('utf-8'))
            
            node = tree.root_node
            depth = 0
            
            block_node_types = {
                'compound_statement',
                'block',
                'function_definition',
                'class_definition',
                'if_statement',
                'for_statement',
                'while_statement',
                'declaration_list',
            }
            
            while True:
                found_child = False
                for child in node.children:
                    if child.start_byte <= byte_offset <= child.end_byte:
                        if child.type in block_node_types:
                            depth += 1
                        node = child
                        found_child = True
                        break
                if not found_child:
                    break
                    
            return depth
        except Exception as e:
            print(f"[TreeSitter] Indent analysis failed: {e}")
            return 0

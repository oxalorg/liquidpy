"""Parses for parsing the tag fragments"""

import ast
from io import StringIO
from pathlib import Path
from lark import v_args, Lark, LarkError, Transformer as LarkTransformer
from .tagfrag import (
    TagFragVar, TagFragConst,
    TagFragOpComparison,
    TagFragGetItem,
    TagFragGetAttr,
    TagFragRange,
    TagFragFilter,
    TagFragOutput
)
from ..tagmgr import register_tag
from ..exceptions import TagSyntaxError, TagRenderError

# common grammar file, used to import some common grammar rules
COMMON_GRAMMAR = str(Path(__file__)
                     .parent
                     .joinpath('tags', 'tags.lark')
                     .resolve())

def _load_grammar(str_grammar, path=COMMON_GRAMMAR):
    """Lark doesn't support customizing include paths
    See: https://github.com/lark-parser/lark/issues/603
    """
    grammar = StringIO(str_grammar)
    grammar.name = path
    return grammar

@v_args(inline=True)
class TagTransformer(LarkTransformer):
    """Base transformer class for the tag fragment parser

    Note that the rules defined here are defined in the common grammar
    For those defined for each tag, we need to write new handlers for them,
    as well as those that we want to override here.
    """

    def start(self, expr):
        """The start rule"""
        return expr

    def tags__var(self, varname):
        """The variables"""
        return TagFragVar(varname)

    def tags__expr(self, exprstr):
        """The exprs"""
        return exprstr

    def tags__atom(self, atomnode):
        """The atomics"""
        return atomnode

    def tags__number(self, numstr):
        """The numbers"""
        return TagFragConst(ast.literal_eval(numstr))

    def tags__op_comparison(self, left, op, right):
        """The operator comparisons"""
        return TagFragOpComparison(left, op, right)

    def tags__getitem(self, obj, subscript):
        """The getitem operation"""
        return TagFragGetItem(obj, subscript)

    def tags__getattr(self, obj, attr):
        """The getattr operation"""
        return TagFragGetAttr(obj, attr)

    def tags__string(self, quoted_string):
        """The strings"""
        # use ast.literal_eval as well?
        return TagFragConst(quoted_string[1:-1]
                            .replace('\\\'', '\'')
                            .replace('\\"', '"'))
    def tags__nil(self):
        """The nil constant"""
        return TagFragConst(None)

    def tags__true(self):
        """The true constant"""
        return TagFragConst(True)

    def tags__false(self):
        """The false constant"""
        return TagFragConst(False)

    def tags__range(self, start, end):
        """The range from start to end"""
        return TagFragRange(start, end)

    def tags__filter(self, filtername):
        return TagFragFilter(filtername)

    def tags__filter_args(self, *exprs):
        return exprs

    def tags__expr_filter(self, filtername, filter_args=None):
        # TagFragFilter, (arg1, arg2, ...)
        return (filtername, filter_args or ())

    def tags__output(self, expr, *expr_filters):
        return TagFragOutput(expr, expr_filters)


    # parse these separately to implement precedence
    tags__contains = tags__op_comparison
    tags__logical_or = tags__op_comparison
    tags__logical_and = tags__op_comparison

class Tag:
    """Tag class, for the Tags defined in the template
    such as `{% ... %}`, `{% ... %}`, as well as the literals

    Properties:
        name (str): The name of the tag
        data (lark.Tree): The parsed tag data
        context (TagContext): The context of this tag in the template
        frag_rendered: The rendered object for fragments in this tag,
            generated in render function and may be used by its children
        parsed (TagParsed): Parsed object from the tag data
        children (list): List of children of the tag
        parent (Tag): The parent tag
        prev (Tag): The previous tag
        next (Tag): The next tag
    """

    # whether the tag is void, meaning True if there is no children allow
    # otherwise False
    VOID = False
    # The syntax of this tag
    SYNTAX = None
    # The transform for the parser of this tag
    TRANSFORMER = TagTransformer
    # Prior tags pattern, used to valiate if this tag is in the right
    # position.
    # This should be a pyparsing object able to match the prior tags
    # This is a list since a tag can be with multiple tags,
    # For example, "else" with "if", "for" and "case"
    PRIOR_TAGS = None
    # Parent tags where this tags allows to be put in
    PARENT_TAGS = None

    def __init__(self, tagname, tagdata, tagcontext):
        self.name = tagname
        self.data = tagdata
        self.context = tagcontext
        self.frag_rendered = None
        # The children of this tag
        self.children = []
        # Parent, previous and next tag object
        self.parent = self.prev = self.next = None
        self.parsed = self.parse()

    def _children_rendered(self, local_envs, global_envs):
        """Render the children
        This will be done recursively to render the whole template
        """
        rendered = ''
        for child in self.children:
            child_rendered, local_envs = child.render(local_envs, global_envs)
            rendered += child_rendered
        return rendered

    def _parent_check(self):
        """Check if we have valid direct or indirect parents

        This is done after parent and prev have been assigned
        """
        # I don't require any parents
        # or I optionally require some
        # pylint: disable=unsupported-membership-test
        if not self.PARENT_TAGS or '' in self.PARENT_TAGS:
            return True

        # Checking for direct parents? TODO?
        if not self.parent:
            return False

        parent = self.parent
        while parent:
            if parent.name in self.PARENT_TAGS:
                return True
            parent = parent.parent
        return False


    def _format_error(self, error=''):
        if isinstance(error, Exception):
            error = f"[{error.__class__.__name__}] {error}\n"
        elif callable(error):
            error = f"[{error.__name__}] {error}\n"
        elif error:
            error = f"{error}\n"
        else:
            error = ''

        formatted = [
            error,
            f'{self.context.template_name}:'
            f'{self.context.line}:{self.context.column}',
            '-' * 80
        ]
        context_lines = self.context.context_getter(line=self.context.line)
        lineno_width = len(str(max(context_lines)))
        for lineno, line in context_lines.items():
            indicator = ('>' if self.context.line == lineno
                         else ' ')
            formatted.append(f'{indicator} {str(lineno).ljust(lineno_width)}'
                             f'. {line}')

        return '\n'.join(formatted) + '\n'


    def _most_prior(self):
        """Find the most prior tag"""
        prior = self.prev
        if not prior:
            return None
        while prior:
            if not prior.prev:
                return prior
            prior = prior.prev
        return None # pragma: no cover

    def parse(self):
        """Parse the fragments of this tag for later processing

        Returns:
            Tag: The parsed tag object
        """
        if self.SYNTAX == '<EMPTY>':
            if self.data:
                raise TagSyntaxError(
                    self._format_error(f'No data allowed for tag {self}')
                )
            self.SYNTAX = None # pylint: disable=invalid-name

        if not self.SYNTAX:
            return None
        syntax = _load_grammar(self.SYNTAX)
        # // TODO: put transformer in Lark to make it faster in prodction stage
        parser = Lark(syntax, parser='earley')
        try:
            tree = parser.parse(self.data)
        except LarkError as lerr:
            raise TagSyntaxError(self._format_error(lerr)) from None

        return self.TRANSFORMER().transform(tree)

    def _render(self, local_envs, # pylint: disable=unused-argument
                global_envs):     # pylint: disable=unused-argument
        """A function for sub-classes to implement

        We don't have to handle local/global envs, as it is handled
        by `render`. Here we only need to take care of the rendering
        """
        return str(self.data)

    def render(self, local_envs, global_envs):
        """Render the tag

        By default, we just render directly whatever in the data, act
        like a literal tag

        Note that this function has to return the envs
        """
        if self.parsed:
            try:
                self.frag_rendered = self.parsed.render(local_envs, global_envs)
            except Exception as exc:
                raise TagRenderError(self._format_error(exc))
        return self._render(local_envs, global_envs), local_envs

    def __repr__(self):
        data = str(self.data)
        shortened_data = (
            data[:17] + '...'
            if len(data) > 20
            else data
        )
        return (f'<Tag(name={self.name}, '
                f'data={shortened_data!r}, '
                f'children={len(self.children)})>')

@register_tag('__LITERAL__')
class TagLiteral(Tag):
    """The literal tag"""
    VOID = True

@register_tag('__ROOT__')
class TagRoot(Tag):
    """The virtual root tag with all the direct children
    So we can render this tag so that the whole template
    will be rendered recursively
    """

    def _render(self, local_envs, global_envs):
        """Render all children"""
        return self._children_rendered(local_envs, global_envs)
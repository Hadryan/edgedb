#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2020-present MagicStack Inc. and the EdgeDB authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either nodeess or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


"""EdgeQL expression normalization functions."""


from __future__ import annotations
from typing import *

import copy
import functools

from edb.common.ast import base
from edb.edgeql import ast as qlast
from edb.schema import expraliases as s_aliases
from edb.schema import schema as s_schema
from edb.schema import types as s_types
from edb.schema import name as sn


@functools.singledispatch
def normalize(
    node: Any,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> Any:
    raise ValueError(f'normalize: cannot handle {node!r}')


def _normalize_generic_field(
    node: qlast.Base,
    field: str,
    value: Any,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> None:
    if isinstance(value, qlast.Base):
        setattr(
            node,
            field,
            normalize(
                value,
                schema=schema,
                modaliases=modaliases,
                ignorenames=ignorenames,
            )
        )
    elif isinstance(value, list):
        if value and isinstance(value[0], qlast.Base):
            setattr(
                node,
                field,
                [
                    normalize(
                        el,
                        schema=schema,
                        modaliases=modaliases,
                        ignorenames=ignorenames,
                    ) for el in value
                ]
            )


@normalize.register
def normalize_Base(
    node: qlast.Base,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> qlast.Base:
    node = copy.copy(node)

    for field, value in base.iter_fields(node):
        _normalize_generic_field(
            node,
            field,
            value,
            schema=schema,
            modaliases=modaliases,
            ignorenames=ignorenames,
        )

    return node


@normalize.register
def normalize_DDL(
    node: qlast.DDL,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> qlast.DDL:
    raise ValueError(f'normalize: cannot handle {node!r}')


def _normalize_with_block(
    node: qlast.Statement,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> Tuple[str]:

    # Update the default aliases, modaliases, and ignorenames.
    newaliases = []

    for alias in node.aliases:
        if isinstance(alias, qlast.ModuleAliasDecl):
            if alias.alias:
                modaliases[alias.alias] = alias.module
                newaliases.append(alias)
            else:
                modaliases[None] = alias.module
        else:
            assert isinstance(alias, qlast.AliasedExpr)
            alias.expr = normalize(
                alias.expr,
                schema=schema,
                modaliases=modaliases,
                ignorenames=ignorenames,
            )
            newaliases.append(alias)
            ignorenames = (alias.alias, *ignorenames)

    node.aliases = newaliases

    return ignorenames


def _normalize_aliased_field(
    node: Union[qlast.SubjectMixin, qlast.ReturningMixin, qlast.ForQuery],
    fname: str,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> Tuple[str]:

    # Potentially the result defines an alias that is visible in other
    # clauses
    val = getattr(node, fname)
    setattr(
        node,
        fname,
        normalize(
            val,
            schema=schema,
            modaliases=modaliases,
            ignorenames=ignorenames,
        )
    )
    alias = getattr(node, f'{fname}_alias', None)
    if alias:
        ignorenames = (alias, *ignorenames)

    return ignorenames


@normalize.register
def normalize_SelectQuery(
    node: qlast.SelectQuery,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> qlast.SelectQuery:

    node = copy.copy(node)

    # Process WITH block
    ignorenames = _normalize_with_block(
        node,
        schema=schema,
        modaliases=modaliases,
        ignorenames=ignorenames,
    )

    # Process the result expression
    ignorenames = _normalize_aliased_field(
        node,
        'result',
        schema=schema,
        modaliases=modaliases,
        ignorenames=ignorenames,
    )

    for field in ('where', 'orderby', 'offset', 'limit'):
        value = getattr(node, field, None)
        _normalize_generic_field(
            node,
            field,
            value,
            schema=schema,
            modaliases=modaliases,
            ignorenames=ignorenames,
        )

    return node


@normalize.register
def normalize_InsertQuery(
    node: qlast.InsertQuery,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> qlast.InsertQuery:

    node = copy.copy(node)

    # Process WITH block
    ignorenames = _normalize_with_block(
        node,
        schema=schema,
        modaliases=modaliases,
        ignorenames=ignorenames,
    )

    # Process the subject expression
    ignorenames = _normalize_aliased_field(
        node,
        'subject',
        schema=schema,
        modaliases=modaliases,
        ignorenames=ignorenames,
    )

    for field in ('shape',):
        value = getattr(node, field, None)
        _normalize_generic_field(
            node,
            field,
            value,
            schema=schema,
            modaliases=modaliases,
            ignorenames=ignorenames,
        )

    return node


@normalize.register
def normalize_UpdateQuery(
    node: qlast.UpdateQuery,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> qlast.UpdateQuery:

    node = copy.copy(node)

    # Process WITH block
    ignorenames = _normalize_with_block(
        node,
        schema=schema,
        modaliases=modaliases,
        ignorenames=ignorenames,
    )

    # Process the subject expression
    ignorenames = _normalize_aliased_field(
        node,
        'subject',
        schema=schema,
        modaliases=modaliases,
        ignorenames=ignorenames,
    )

    for field in ('where', 'shape',):
        value = getattr(node, field, None)
        _normalize_generic_field(
            node,
            field,
            value,
            schema=schema,
            modaliases=modaliases,
            ignorenames=ignorenames,
        )

    return node


@normalize.register
def normalize_DeleteQuery(
    node: qlast.DeleteQuery,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> qlast.DeleteQuery:

    node = copy.copy(node)

    # Process WITH block
    ignorenames = _normalize_with_block(
        node,
        schema=schema,
        modaliases=modaliases,
        ignorenames=ignorenames,
    )

    # Process the subject expression
    ignorenames = _normalize_aliased_field(
        node,
        'subject',
        schema=schema,
        modaliases=modaliases,
        ignorenames=ignorenames,
    )

    for field in ('where', 'orderby', 'offset', 'limit'):
        value = getattr(node, field, None)
        _normalize_generic_field(
            node,
            field,
            value,
            schema=schema,
            modaliases=modaliases,
            ignorenames=ignorenames,
        )

    return node


@normalize.register
def normalize_ForQuery(
    node: qlast.ForQuery,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> qlast.ForQuery:

    node = copy.copy(node)

    # Process WITH block
    ignorenames = _normalize_with_block(
        node,
        schema=schema,
        modaliases=modaliases,
        ignorenames=ignorenames,
    )

    # Process the iterator expression
    ignorenames = _normalize_aliased_field(
        node,
        'iterator',
        schema=schema,
        modaliases=modaliases,
        ignorenames=ignorenames,
    )

    # Process the result expression
    ignorenames = _normalize_aliased_field(
        node,
        'result',
        schema=schema,
        modaliases=modaliases,
        ignorenames=ignorenames,
    )

    return node


@normalize.register
def normalize_GroupQuery(
    node: qlast.GroupQuery,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> qlast.GroupQuery:
    raise ValueError(f'normalize: cannot handle {node!r}')


@normalize.register
def compile_Path(
    node: qlast.Path,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> qlast.Path:

    node = copy.copy(node)

    # We only need to resolve non-partial paths
    if not node.partial:
        steps = []
        for step in node.steps:
            if isinstance(step, (qlast.Expr, qlast.TypeIntersection)):
                steps.append(
                    normalize(
                        step,
                        schema=schema,
                        modaliases=modaliases,
                        ignorenames=ignorenames,
                    )
                )
            elif isinstance(step, qlast.ObjectRef):
                # This is a specific path root, resolve it.
                if not step.module and step.name not in ignorenames:
                    obj = schema.get(
                        step.name,
                        default=None,
                        module_aliases=modaliases,
                    )
                    if obj is not None:
                        step.module = obj.get_name(schema).module
                    elif None in modaliases:
                        # Even if the name was not resolved in the
                        # schema it may be the name of the object
                        # being defined, as such the default module
                        # should be used. Names that must be ignored
                        # (like aliases and parameters) have already
                        # been filtered by the ignorenames.
                        step.module = modaliases[None]
                steps.append(step)
            else:
                steps.append(step)

        node.steps = steps

    return node


@normalize.register
def compile_FunctionCall(
    node: qlast.FunctionCall,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> qlast.FunctionCall:

    node = copy.copy(node)

    if isinstance(node.func, str) and node.func not in ignorenames:
        funcs = schema.get_functions(
            node.func, default=tuple(), module_aliases=modaliases)
        if funcs:
            # As long as we found some functions, they will be from
            # the same module (the first valid resolved module for the
            # function name will mask "std").
            _, fname = funcs[0].get_name(schema).as_tuple()
            _, module, name = sn.split_name(sn.shortname_from_fullname(fname))
            node.func = (module, name)
        elif None in modaliases:
            # Even if the name was not resolved in the schema it may
            # be the name of the object being defined, as such the
            # default module should be used. Names that must be
            # ignored (like aliases and parameters) have already been
            # filtered by the ignorenames.
            node.func = (modaliases[None], node.func)

    node.args = [
        normalize(
            arg,
            schema=schema,
            modaliases=modaliases,
            ignorenames=ignorenames,
        ) for arg in node.args
    ]
    node.kwargs = {
        key: normalize(val,
                       schema=schema,
                       modaliases=modaliases,
                       ignorenames=ignorenames)
        for key, val in node.kwargs.items()
    }

    return node


@normalize.register
def compile_TypeName(
    node: qlast.TypeName,
    *,
    schema: s_schema.Schema,
    modaliases: Mapping[Optional[str], str],
    ignorenames: Sequence[str] = tuple(),
) -> qlast.TypeName:

    node = copy.copy(node)

    # Resolve the main type
    if isinstance(node.maintype, qlast.ObjectRef):
        # This is a specific path root, resolve it.
        if (not node.maintype.module and
                # maintype names 'array' and 'tuple' specifically
                # should also be ignored
                node.maintype.name not in {'array', 'tuple', *ignorenames}):
            maintype = schema.get(
                node.maintype.name,
                default=None,
                module_aliases=modaliases,
            )

            if maintype is not None:
                node.maintype.module = maintype.get_name(schema).module
            elif None in modaliases:
                # Even if the name was not resolved in the schema it
                # may be the name of the object being defined, as such
                # the default module should be used. Names that must
                # be ignored (like aliases and parameters) have
                # already been filtered by the ignorenames.
                node.maintype.module = modaliases[None]

    if node.subtypes is not None:
        node.subtypes = [
            normalize(
                st,
                schema=schema,
                modaliases=modaliases,
                ignorenames=ignorenames,
            ) for st in node.subtypes
        ]

    return node

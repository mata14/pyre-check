# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import unittest
from unittest.mock import MagicMock, call, patch

from .. import connection, query


class QueryAPITest(unittest.TestCase):
    def test_defines(self) -> None:
        pyre_connection = MagicMock()
        pyre_connection.query_server.return_value = {
            "response": [
                {
                    "name": "a.foo",
                    "parameters": [{"name": "x", "annotation": "int"}],
                    "return_annotation": "int",
                }
            ]
        }
        self.assertEqual(
            query.defines(pyre_connection, ["a"]),
            [
                query.Define(
                    name="a.foo",
                    parameters=[query.DefineParameter(name="x", annotation="int")],
                    return_annotation="int",
                )
            ],
        )
        pyre_connection.query_server.side_effect = [
            {
                "response": [
                    {
                        "name": "a.foo",
                        "parameters": [{"name": "x", "annotation": "int"}],
                        "return_annotation": "int",
                    }
                ]
            },
            {
                "response": [
                    {
                        "name": "b.bar",
                        "parameters": [{"name": "y", "annotation": "str"}],
                        "return_annotation": "int",
                    }
                ]
            },
        ]
        self.assertEqual(
            query.defines(pyre_connection, ["a", "b"], batch_size=1),
            [
                query.Define(
                    name="a.foo",
                    parameters=[query.DefineParameter(name="x", annotation="int")],
                    return_annotation="int",
                ),
                query.Define(
                    name="b.bar",
                    parameters=[query.DefineParameter(name="y", annotation="str")],
                    return_annotation="int",
                ),
            ],
        )
        with patch(f"{query.__name__}._defines") as defines_implementation:
            defines_implementation.return_value = []
            query.defines(pyre_connection, ["a", "b", "c", "d"], batch_size=2)
            defines_implementation.assert_has_calls(
                [call(pyre_connection, ["a", "b"]), call(pyre_connection, ["c", "d"])]
            )
            defines_implementation.reset_calls()
            query.defines(
                pyre_connection, ["a", "b", "c", "d", "e", "f", "g"], batch_size=2
            )
            defines_implementation.assert_has_calls(
                [
                    call(pyre_connection, ["a", "b"]),
                    call(pyre_connection, ["c", "d"]),
                    call(pyre_connection, ["e", "f"]),
                    call(pyre_connection, ["g"]),
                ]
            )
        with self.assertRaises(ValueError):
            query.defines(pyre_connection, ["a", "b"], batch_size=0)

        with self.assertRaises(ValueError):
            query.defines(pyre_connection, ["a", "b"], batch_size=-1)

    def test_get_class_hierarchy(self) -> None:
        pyre_connection = MagicMock()
        pyre_connection.query_server.return_value = {
            "response": [{"Foo": ["object"]}, {"object": []}]
        }
        hierarchy = query.get_class_hierarchy(pyre_connection)
        assert hierarchy is not None
        self.assertEqual(hierarchy.hierarchy, {"Foo": ["object"], "object": []})
        # Reverse hierarchy.
        self.assertEqual(hierarchy.reverse_hierarchy, {"object": ["Foo"], "Foo": []})
        # Superclasses.
        self.assertEqual(hierarchy.superclasses("Foo"), ["object"])
        self.assertEqual(hierarchy.superclasses("object"), [])
        self.assertEqual(hierarchy.superclasses("Nonexistent"), [])
        # Subclasses.
        self.assertEqual(hierarchy.subclasses("object"), ["Foo"])
        self.assertEqual(hierarchy.subclasses("Foo"), [])
        self.assertEqual(hierarchy.subclasses("Nonexistent"), [])

        pyre_connection.query_server.return_value = {
            "response": [
                {"Foo": ["object"]},
                {"object": []},
                # This should never happen in practice, but unfortunately is something
                # to consider due to the type of the JSON returned. The last entry wins.
                {"Foo": ["Bar", "Baz"]},
                {"Bar": ["object"]},
            ]
        }
        class_hierarchy = query.get_class_hierarchy(pyre_connection)
        assert class_hierarchy is not None
        self.assertEqual(
            class_hierarchy.hierarchy,
            {"Foo": ["Bar", "Baz"], "Bar": ["object"], "object": []},
        )
        self.assertEqual(class_hierarchy.superclasses("Foo"), ["Bar", "Baz"])

    def test_get_superclasses(self) -> None:
        pyre_connection = MagicMock()
        pyre_connection.query_server.return_value = {
            "response": [{"Scooter": ["Bike", "Vehicle", "object"]}]
        }
        self.assertEqual(
            query.get_superclasses(pyre_connection, "Scooter"),
            ["Bike", "Vehicle", "object"],
        )

    def test_get_attributes(self) -> None:
        pyre_connection = MagicMock()
        pyre_connection.query_server.return_value = {
            "response": [
                {
                    "response": {
                        "attributes": [
                            {"annotation": "int", "name": "a"},
                            {
                                "annotation": "typing.Callable(a.C.foo)[[], str]",
                                "name": "foo",
                            },
                        ]
                    }
                }
            ]
        }
        self.assertEqual(
            query.get_attributes(pyre_connection, ["a.C"]),
            {
                "a.C": [
                    query.Attributes(name="a", annotation="int"),
                    query.Attributes(
                        name="foo", annotation="typing.Callable(a.C.foo)[[], str]"
                    ),
                ]
            },
        )

    def test_get_attributes_batch(self) -> None:
        pyre_connection = MagicMock()
        pyre_connection.query_server.return_value = {
            "response": [
                {
                    "response": {
                        "attributes": [
                            {"annotation": "int", "name": "a"},
                            {
                                "annotation": "typing.Callable(a.C.foo)[[], str]",
                                "name": "foo",
                            },
                        ]
                    }
                },
                {
                    "response": {
                        "attributes": [
                            {"annotation": "str", "name": "b"},
                            {"annotation": None, "name": "c"},
                        ]
                    }
                },
            ]
        }
        self.assertEqual(
            query.get_attributes(
                pyre_connection,
                [
                    "TestClassA",
                    "TestClassB",
                ],
                batch_size=100,
            ),
            {
                "TestClassA": [
                    query.Attributes(name="a", annotation="int"),
                    query.Attributes(
                        name="foo", annotation="typing.Callable(a.C.foo)[[], str]"
                    ),
                ],
                "TestClassB": [
                    query.Attributes(name="b", annotation="str"),
                    query.Attributes(name="c", annotation=None),
                ],
            },
        )

    def test_get_attributes_batch_no_size(self) -> None:
        pyre_connection = MagicMock()
        pyre_connection.query_server.return_value = {
            "response": [
                {
                    "response": {
                        "attributes": [
                            {"annotation": "int", "name": "a"},
                            {
                                "annotation": "typing.Callable(a.C.foo)[[], str]",
                                "name": "foo",
                            },
                        ]
                    }
                },
                {
                    "response": {
                        "attributes": [
                            {"annotation": "str", "name": "b"},
                            {"annotation": None, "name": "c"},
                        ]
                    }
                },
            ]
        }
        self.assertEqual(
            query.get_attributes(
                pyre_connection,
                [
                    "TestClassA",
                    "TestClassB",
                ],
                batch_size=None,
            ),
            {
                "TestClassA": [
                    query.Attributes(name="a", annotation="int"),
                    query.Attributes(
                        name="foo", annotation="typing.Callable(a.C.foo)[[], str]"
                    ),
                ],
                "TestClassB": [
                    query.Attributes(name="b", annotation="str"),
                    query.Attributes(name="c", annotation=None),
                ],
            },
        )

    def test_get_call_graph(self) -> None:
        pyre_connection = MagicMock()
        pyre_connection.query_server.return_value = {
            "response": {
                "async_test.foo": [],
                "async_test.bar": [
                    {
                        "locations": [
                            {
                                "path": "async_test.py",
                                "start": {"line": 6, "column": 4},
                                "stop": {"line": 6, "column": 7},
                            }
                        ],
                        "kind": "function",
                        "target": "async_test.foo",
                    }
                ],
                "async_test.C.method": [
                    {
                        "locations": [
                            {
                                "path": "async_test.py",
                                "start": {"line": 10, "column": 4},
                                "stop": {"line": 10, "column": 7},
                            }
                        ],
                        "kind": "method",
                        "is_optional_class_attribute": False,
                        "direct_target": "async_test.C.method",
                        "class_name": "async_test.C",
                        "dispatch": "dynamic",
                    }
                ],
            }
        }

        self.assertEqual(
            query.get_call_graph(pyre_connection),
            {
                "async_test.foo": [],
                "async_test.bar": [
                    query.CallGraphTarget(
                        {
                            "target": "async_test.foo",
                            "kind": "function",
                            "locations": [
                                {
                                    "path": "async_test.py",
                                    "start": {"line": 6, "column": 4},
                                    "stop": {"line": 6, "column": 7},
                                }
                            ],
                        }
                    )
                ],
                "async_test.C.method": [
                    query.CallGraphTarget(
                        {
                            "target": "async_test.C.method",
                            "kind": "method",
                            "locations": [
                                {
                                    "path": "async_test.py",
                                    "start": {"line": 10, "column": 4},
                                    "stop": {"line": 10, "column": 7},
                                }
                            ],
                        }
                    )
                ],
            },
        )

    def test_get_invalid_taint_models(self) -> None:
        pyre_connection = MagicMock()
        pyre_connection.query_server.side_effect = connection.PyreQueryError(
            "Invalid model for `path.to.first.model` defined in `/path/to/first.py:11`"
            + ": Modeled entity is not part of the environment!"
        )
        self.assertEqual(
            query.get_invalid_taint_models(pyre_connection),
            [
                query.InvalidModel(
                    fully_qualified_name="path.to.first.model",
                    path="/path/to/first.py",
                    line=11,
                    full_error_message="Invalid model for `path.to.first.model` "
                    + "defined in `/path/to/first.py:11`: Modeled entity is "
                    + "not part of the environment!",
                )
            ],
        )

        pyre_connection = MagicMock()
        pyre_connection.query_server.side_effect = connection.PyreQueryError(
            "Invalid model for `path.to.first.model` defined in `/path/to/"
            + "first.py:11`: Modeled entity is not part of the environment!\n"
            + "Invalid model for `path.to.second.model` defined in `/path/to/"
            + "second.py:22`: Modeled entity is not part of the environment!\n"
            + "Invalid model for `path.to.third.model` defined in `/path/to/"
            + "third.py:33`: Modeled entity is not part of the environment!"
        )
        self.assertEqual(
            query.get_invalid_taint_models(pyre_connection),
            [
                query.InvalidModel(
                    fully_qualified_name="path.to.first.model",
                    path="/path/to/first.py",
                    line=11,
                    full_error_message="Invalid model for `path.to.first.model` "
                    + "defined in `/path/to/first.py:11`: Modeled entity is "
                    + "not part of the environment!",
                ),
                query.InvalidModel(
                    fully_qualified_name="path.to.second.model",
                    path="/path/to/second.py",
                    line=22,
                    full_error_message="Invalid model for `path.to.second.model` "
                    + "defined in `/path/to/second.py:22`: Modeled entity is "
                    + "not part of the environment!",
                ),
                query.InvalidModel(
                    fully_qualified_name="path.to.third.model",
                    path="/path/to/third.py",
                    line=33,
                    full_error_message="Invalid model for `path.to.third.model` "
                    + "defined in `/path/to/third.py:33`: Modeled entity is "
                    + "not part of the environment!",
                ),
            ],
        )

        pyre_connection = MagicMock()
        pyre_connection.query_server.side_effect = connection.PyreQueryError(
            "This is an invalid error message"
        )
        with self.assertRaises(connection.PyreQueryError):
            query.get_invalid_taint_models(pyre_connection)
        pyre_connection = MagicMock()
        pyre_connection.query_server.return_value = {
            "response": {
                "errors": [
                    {
                        "description": "Invalid model for `first.f`: Unrecognized taint annotation `NotAnAnnotation`",  # noqa: B950
                        "path": "/path/to/first.py",
                        "line": 2,
                        "column": 0,
                    }
                ]
            }
        }
        self.assertEqual(
            query.get_invalid_taint_models(pyre_connection),
            [
                query.InvalidModel(
                    fully_qualified_name="",
                    path="/path/to/first.py",
                    line=2,
                    full_error_message="Invalid model for `first.f`: Unrecognized taint annotation `NotAnAnnotation`",  # noqa: B950
                ),
            ],
        )

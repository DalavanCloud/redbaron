import sys
import baron
from types import ModuleType
from UserList import UserList

from .utils import indent


def to_node(node):
    class_name = "".join(map(lambda x: x.capitalize(), node["type"].split("_"))) + "Node"
    if class_name in globals():
        return globals()[class_name](node)
    else:
        return type(class_name, (Node,), {})(node)


class NodeList(UserList):
    def find(self, identifier, recursive=True, **kwargs):
        for i in self.data:
            candidate = i.find(identifier, recursive=recursive, **kwargs)
            if candidate is not None:
                return candidate

    def __getattr__(self, key):
        return self.find(key)

    def fst(self):
        return [x.fst() for x in self.data]

    def __repr__(self):
        to_return = ""
        for number, value in enumerate(self.data):
            to_return += ("%-3s " % number) + "\n    ".join(value.__repr__().split("\n"))
            to_return += "\n"
        return to_return
        return "%s" % [x.__repr__() for x in self.data]

    def help(self):
        for num, i in enumerate(self.data):
            print num, "-----------------------------------------------------"
            print i.__help__()

    def __help__(self):
        return [x.__help__() for x in self.data]


class Node(object):
    def __init__(self, node):
        self._str_keys = []
        self._list_keys = []
        self._dict_keys = []
        for key, value in node.items():
            if isinstance(value, dict):
                if value:
                    setattr(self, key, to_node(value))
                else:
                    setattr(self, key, None)
                self._dict_keys.append(key)
            elif isinstance(value, list):
                setattr(self, key, NodeList(map(to_node, value)))
                self._list_keys.append(key)
            else:
                setattr(self, key, value)
                self._str_keys.append(key)

    def find(self, identifier, recursive=True, **kwargs):
        all_my_keys = self._str_keys + self._list_keys + self._dict_keys
        if identifier.lower() in self._generate_identifiers():
            for key in kwargs:
                if key not in all_my_keys:
                    break

                if getattr(self, key) != kwargs[key]:
                    break

            else:  # else it match so the else clause will be used
                   # (for once that this else stuff is usefull)
                return self

        if recursive:
            for i in self._dict_keys:
                i = getattr(self, i)
                if not i:
                    continue

                found = i.find(identifier, recursive, **kwargs)
                if found:
                    return found

            for key in self._list_keys:
                for i in getattr(self, key):
                    found = i.find(identifier, recursive, **kwargs)
                    if found:
                        return found

    def __getattr__(self, key):
        return self.find(key)

    def _generate_identifiers(self):
        return map(lambda x: x.lower(), [self.type, self.__class__.__name__, self.__class__.__name__.replace("Node", ""), self.type + "_"])

    def fst(self):
        to_return = {}
        for key in self._str_keys:
            to_return[key] = getattr(self, key)
        for key in self._list_keys:
            to_return[key] = [node.fst() for node in getattr(self, key)]
        for key in self._dict_keys:
            if getattr(self, key):
                to_return[key] = getattr(self, key).fst()
            else:
                to_return[key] = {}
        return to_return

    def help(self, with_formatting=False):
        print self.__help__(with_formatting)

    def __help__(self, with_formatting=False):
        to_join = ["%s()" % self.__class__.__name__]
        to_join += ["%s=%s" % (key, repr(getattr(self, key))) for key in self._str_keys if key != "type" and "formatting" not in key]
        to_join += ["%s ->\n  %s" % (key, indent(getattr(self, key).__help__(), "    ").lstrip() if getattr(self, key) else getattr(self, key)) for key in self._dict_keys if "formatting" not in key]

        # need to do this otherwise I end up with stacked quoted list
        # example: value=[\'DottedAsNameNode(target=\\\'None\\\', as=\\\'False\\\', value=DottedNameNode(value=["NameNode(value=\\\'pouet\\\')"])]
        for key in filter(lambda x: "formatting" not in x, self._list_keys):
            to_join.append(("%s ->" % key))
            for i in getattr(self, key):
                to_join.append("  * " + indent(i.__help__(), "      ").lstrip())

        if with_formatting:
            to_join += ["%s=%s" % (key, repr(getattr(self, key))) for key in self._str_keys if key != "type" and "formatting" in key]
            to_join += ["%s=%s" % (key, getattr(self, key).__help__() if getattr(self, key) else getattr(self, key)) for key in self._dict_keys if "formatting" in key]

            for key in filter(lambda x: "formatting" in x, self._list_keys):
                to_join.append(("%s ->" % key))
                for i in getattr(self, key):
                    to_join.append("  * " + indent(i.__help__(), "  ").lstrip())

        return "\n  ".join(to_join)

    def __repr__(self):
        return baron.dumps([self.fst()])


class IntNode(Node):
    def __init__(self, node):
        super(IntNode, self).__init__(node)
        #self.value = int(self.value)


class EndlNode(Node):
    def __repr__(self):
        return repr(baron.dumps([self.fst()]))


# enter the black magic realm, beware of what you might find
# (in fact that's pretty simple appart from the strange stuff needed)
# this basically allows to write code like:
# from redbaron.nodes import WatheverNode
# and a new class with Node has the parent will be created on the fly
# if this class doesn't already exist (like IntNode for example)
# while this is horribly black magic, this allows quite some cool stuff
class MissingNodesBuilder(dict):
    def __init__(self, globals, baked_args={}):
        self.globals = globals
        self.baked_args = baked_args

    def __getitem__(self, key):
        if key in self.globals:
            return self.globals[key]

        if key.endswith("Node"):
            new_node_class = type(key, (Node,), {})
            self.globals[key] = new_node_class
            return new_node_class


class BlackMagicImportHook(ModuleType):
    def __init__(self, self_module, baked_args={}):
        # this code is directly inspired by amoffat/sh
        # see https://github.com/amoffat/sh/blob/80af5726d8aa42017ced548abbd39b489068922a/sh.py#L1695
        for attr in ["__builtins__", "__doc__", "__name__", "__package__"]:
            setattr(self, attr, getattr(self_module, attr))

        # python 3.2 (2.7 and 3.3 work fine) breaks on osx (not ubuntu)
        # if we set this to None. and 3.3 needs a value for __path__
        self.__path__ = []
        self.self_module = self_module
        self._env = MissingNodesBuilder(globals(), baked_args)

    def __getattr__(self, name):
        return self._env[name]

    def __setattr__(self, name, value):
        if hasattr(self, "_env"):
            self._env[name] = value
        ModuleType.__setattr__(self, name, value)


self = sys.modules[__name__]
sys.modules[__name__] = BlackMagicImportHook(self)

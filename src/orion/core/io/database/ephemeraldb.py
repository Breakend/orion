# -*- coding: utf-8 -*-
"""
:mod:`orion.core.io.database.ephemeraldb` -- Non permanent database
===================================================================

.. module:: database
   :platform: Unix
   :synopsis: Implement non permanent version of :class:`orion.core.io.database.AbstractDB`

"""
from collections import defaultdict
import copy

from orion.core.io.database import AbstractDB, DuplicateKeyError


class EphemeralDB(AbstractDB):
    """Non permanent database

    This database is meant for debugging purposes. It only lives through one execution and all
    information saved during it is lost when the process is terminated.

    .. seealso:: :class:`orion.core.io.database.AbstractDB` for more on attributes.

    """

    @property
    def is_connected(self):
        """Return true, always."""
        return True

    def initiate_connection(self):
        """Create the dictionary which serve as an ephemeral database"""
        self._db = defaultdict(EphemeralCollection)

    def close_connection(self):
        """Remove the dictionary"""
        self._db = None

    def ensure_index(self, collection_name, keys, unique=False):
        """Create given indexes if they do not already exist in database.

        Indexes are only created if `unique` is True.
        """
        self._db[collection_name].create_index(keys, unique=unique)

    def write(self, collection_name, data, query=None):
        """Write new information to a collection. Perform insert or update.

        .. seealso:: :meth:`AbstractDB.write` for argument documentation.

        """
        dbcollection = self._db[collection_name]

        if query is None:
            # We can assume that we do not want to update.
            # So we do insert_many instead.
            if type(data) not in (list, tuple):
                data = [data]
            return dbcollection.insert_many(documents=data)

        update_data = {'$set': data}

        return dbcollection.update_many(query=query,
                                        update=update_data)

    def read(self, collection_name, query=None, selection=None):
        """Read a collection and return a value according to the query.

        .. seealso:: :meth:`AbstractDB.read` for argument documentation.

        """
        dbcollection = self._db[collection_name]

        dbdocs = dbcollection.find(query, selection)

        return dbdocs

    def read_and_write(self, collection_name, query, data, selection=None):
        """Read a collection's document and update the found document.

        Returns the updated document, or None if nothing found.

        .. seealso:: :meth:`AbstractDB.read_and_write` for
                     argument documentation.

        """
        dbdoc = self.read(collection_name, query)
        if not dbdoc:
            return None

        id_query = {'_id': dbdoc[0]['_id']}
        self.write(collection_name, data, id_query)
        return self.read(collection_name, id_query)[0]

    def count(self, collection_name, query=None):
        """Count the number of documents in a collection which match the `query`.

        .. seealso:: :meth:`AbstractDB.count` for argument documentation.

        """
        dbcollection = self._db[collection_name]
        return dbcollection.count(query=query)

    def remove(self, collection_name, query):
        """Delete from a collection document[s] which match the `query`.

        .. seealso:: :meth:`AbstractDB.remove` for argument documentation.

        """
        dbcollection = self._db[collection_name]

        return dbcollection.delete_many(query=query)


class EphemeralCollection(object):
    """Non permanent collection

    This collection is meant for debugging purposes within the EphemeralDB.

    .. seealso:: :class:`orion.core.io.database.ephemeraldb.EphemeralDB` for database object.

    """

    def __init__(self):
        """Initialise the collection, with no documents and only _id unique index."""
        self._documents = []
        self._indexes = dict()
        self.create_index('_id', unique=True)

    def create_index(self, keys, unique=False):
        """Create given indexes if they do not already exist for this collection.

        Indexes are only created if `unique` is True.
        """
        # turn single key into list for coherence
        if not isinstance(keys, (list, tuple)):
            keys = [(keys, None)]

        keys = tuple(key for (key, order) in keys)
        if unique and keys not in self._indexes:
            self._indexes[keys] = set()

            for document in self._documents:
                self._validate_index(document, indexes=[keys])
                self._indexes[keys].add(tuple(document[key] for key in keys))

    def _register_keys(self, document):
        """Register index values of a new document"""
        for index, values in self._indexes.items():
            values.add(tuple(document[key] for key in index))

    def find(self, query=None, selection=None):
        """Find documents in the collection and return a value according to the query.

        .. seealso:: :meth:`AbstractDB.read` for argument documentation.

        """
        found_documents = []
        for document in self._documents:
            if document.match(query):
                found_documents.append(document.select(selection))

        return found_documents

    def _validate_index(self, document, indexes=None):
        """Validate index values of a document

        Raises
        ------
        DuplicateKeyError
            If the document contains unique indexes which are already present in the database.

        """
        if indexes is None:
            indexes = self._indexes.keys()

        for index in indexes:
            document_values = tuple(document[key] for key in index)
            if document_values in self._indexes[index]:
                raise DuplicateKeyError(
                    "Duplicate key error: index={} value={}".format(index, document_values))

    def _get_new_id(self):
        """Return max id + 1"""
        if self._documents:
            return max(d['_id'] for d in self._documents) + 1

        return 1

    def insert_many(self, documents):
        """Add new documents in the collection.

        If the documents do not have a keys `_id`, they are assigned by default
        the max id + 1.

        Raises
        ------
        DuplicateKeyError
            If the document contains unique indexes which are already present in the database.

        """
        for document in documents:
            if '_id' not in document:
                document['_id'] = self._get_new_id()
            ephemeral_document = EphemeralDocument(document)
            self._validate_index(ephemeral_document)
            self._documents.append(ephemeral_document)
            self._register_keys(ephemeral_document)

        return len(documents)

    def update_many(self, query, update):
        """Update documents matching the query

        Raises
        ------
        DuplicateKeyError
            If the update creates a duplication of unique indexes in the database.

        """
        updates = 0
        for document in self._documents:
            if document.match(query):
                document.update(update)
                updates += 1

        return updates

    def _upsert(self, query, update):
        """Insert the document when query was not found.

        If update contains `$set`, then the new document is the combination of query and
        update['$set'], otherwise the new document is `update`.
        """
        if "$set" in update:
            new_document = copy.deepcopy(query)
            new_document.update(update["$set"])
        else:
            new_document = update

        self.insert_many([new_document])

    def count(self, query=None):
        """Count the number of documents in a collection which match the `query`.

        .. seealso:: :meth:`AbstractDB.count` for argument documentation.

        """
        return len(self.find(query))

    def delete_many(self, query=None):
        """Delete from a collection document[s] which match the `query`.

        .. seealso:: :meth:`AbstractDB.remove` for argument documentation.

        """
        deleted = 0
        retained_documents = []
        for document in self._documents:
            if not document.match(query):
                retained_documents.append(document)
            else:
                deleted += 1

        self._documents = retained_documents

        return deleted

    def drop(self):
        """Drop the collection, removing all documents and indexes."""
        self._documents = []
        self._indexes = dict()


class EphemeralDocument(object):
    """Non permanent document

    This document is meant for debugging purposes within the EphemeralDB.

    .. seealso:: :class:`orion.core.io.database.ephemeraldb.EphemeralDB` for database object.

    """

    operators = {
        "$in": (lambda a, b: a in b),
        "$gte": (lambda a, b: a is not None and a >= b),
        "$gt": (lambda a, b: a is not None and a > b),
        "$lte": (lambda a, b: a is not None and a <= b),
    }

    def __init__(self, data):
        """Initialise the document with a flattened version of the data"""
        self._data = _flatten(data)

    def match(self, query=None):
        """Test if the document corresponds to a given query"""
        if query is None or query == {}:
            return True

        query = _flatten(query)
        for key, value in query.items():
            if not self.match_key(key, value):
                return False

        return True

    def _is_operator(self, key):  # pylint: disable=no-self-use
        return key.split(".")[-1].startswith('$')

    def _get_key_operator(self, key):
        operator = key.split(".")[-1]
        key = ".".join(key.split(".")[:-1])

        if operator not in self.operators:
            raise ValueError('Operator \'{}\' is not supported by EphemeralDB'.format(operator))

        return key, self.operators[operator]

    def match_key(self, key, value):
        """Test if a data corresponding to the given key is in agreement with the given
        value based on the operator defined within the key.

        Default operator is equal when no operator is defined.
        Other operators could be $in, $gte, $gt or $lte. They are defined
        in the last section of the key. For example: `abc.def.$in` or `abc.def.$gte`.
        """
        if self._is_operator(key):
            key, operator = self._get_key_operator(key)

            return key in self and operator(self[key], value)

        return key in self and self[key] == value

    def _validate_keys(self, keys):
        """Verify that all keys are 0 or 1 (with exception of _id) and convert them.

        For simplicity, when keys are 0, the inverse set of keys for 1s is computed.

        .. note ::

            _id is set to 1 if not specified. Only _id may be set to 0 if other keys are set to 1.
        """
        if len(keys) == 1 and keys.get('_id', 0) == 1:
            return keys

        keys_without_id = [key for key in keys if key != '_id']
        n_keys = sum(keys[key] for key in keys_without_id)
        if n_keys != 0 and n_keys != len(keys_without_id):
            raise ValueError(
                'Cannot mix selection with 1 and 0s except for _id: {}'.format(keys))

        # All given keys are 0 (with possible exception of _id)
        if n_keys == 0:
            new_keys = dict((key, 1) for key in self._data.keys() if key not in keys)
            new_keys['_id'] = keys.get('_id', 1)
            keys = new_keys

        keys.setdefault('_id', 1)

        return keys

    def select(self, keys):
        """Only select or only drop the specified keys

        For a pair (key, value) in the dictionnary, value=0 means the key will not be included
        while value=1 means it will.

        All specified keys should be 0 or 1. They cannot have different values with the exception
        of _id which can be specified to 0 while the others are at 1. The _id field is always
        returned unless specified with 0.

        Parameters
        ----------
        keys: dict
            Pairs of keys and 0 or 1s. When a key is associated with 1, it is kept in the selection,
            otherwise it is dropped.

        """
        if not keys:
            return _unflatten(self._data)

        keys = _flatten(keys)
        keys = self._validate_keys(keys)

        selection = dict()

        def key_is_match(key, selected_key):
            """Test if key matches the selected key

            key_is_match(abc.def.ghi, abc.def.ghi) -> True
            key_is_match(abc.def.ghi, abc.def) -> True
            key_is_match(abc.def.ghi, abc.de) -> False
            key_is_match(abc.def.ghi, xyz) -> False
            """
            return (key == selected_key or
                    (key.startswith(selected_key) and
                     key.replace(selected_key, '')[0] == "."))

        for key, value in self._data.items():
            for selected_key, include in keys.items():
                if include and key_is_match(key, selected_key):
                    selection[key] = value

        return _unflatten(selection)

    def update(self, data):
        """Update the values of the document.

        Parameters
        ----------
        data: dict
            Dictionary of data to update the document. If `$set` is in
            the data, the corresponding `data[$set]` will be used instead.

        """
        data = _flatten(data.get("$set", data))
        self._data.update(data)

    def to_dict(self):
        """Convert the ephemeral document to a python dictionary"""
        return self.select({})

    def __getitem__(self, key):
        """Get the item corresponding to the given key in the document"""
        return self._data[key]

    def __contains__(self, key):
        """Test whether the given key is present in the document"""
        return key in self._data


def _flatten(dictionary):
    def __flatten(dictionary):
        if dictionary == {}:
            return dictionary

        key, value = dictionary.popitem()
        if not isinstance(value, dict) or not value:
            new_dictionary = {key: value}
            new_dictionary.update(__flatten(dictionary))
            return new_dictionary

        flat_sub_dictionary = __flatten(value)
        for flat_sub_key in list(flat_sub_dictionary.keys()):
            flat_key = key + '.' + flat_sub_key
            flat_sub_dictionary[flat_key] = flat_sub_dictionary.pop(flat_sub_key)

        new_dictionary = flat_sub_dictionary
        new_dictionary.update(_flatten(dictionary))
        return new_dictionary

    return __flatten(copy.deepcopy(dictionary))


def _unflatten(dictionary):
    unflattened_dictionary = dict()
    for key, value in dictionary.items():
        parts = key.split(".")
        sub_dictionary = unflattened_dictionary
        for part in parts[:-1]:
            if part not in sub_dictionary:
                sub_dictionary[part] = dict()
            sub_dictionary = sub_dictionary[part]
        sub_dictionary[parts[-1]] = value
    return unflattened_dictionary

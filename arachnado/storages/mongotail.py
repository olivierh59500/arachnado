import pymongo
from bson.objectid import ObjectId
from tornado.gen import sleep, coroutine

from arachnado.storages.mongo import MongoStorage


class MongoTailStorage(MongoStorage):
    fetch_delay = 0

    def __init__(self, *args, **kwargs):
        super(MongoTailStorage, self).__init__(*args, **kwargs)
        self.tailing = False
        self.signals['tailed'] = object()

    def subscribe(self, subscriptions, callback, last_id=None, query=None,
                  fields=None):
        if 'tailed' in subscriptions:
            self.tail(query, fields, last_id)
        super(MongoTailStorage, self).subscribe(subscriptions, callback)

    def unsubscribe(self, subscriptions):
        if 'tailed' in subscriptions:
            self.untail()

    @coroutine
    def tail(self, query=None, fields=None, last_object_id=None):
        if self.tailing:
            raise RuntimeError('This storage is already tailing')
        self.tailing = True
        if isinstance(last_object_id, basestring):
            last_object_id = ObjectId(last_object_id)

        if query is not None:
            query = self._objectify(query)

        def tail_query():
            if last_object_id is None or last_object_id == 0:
                if query is None:
                    return {}
                else:
                    return query
            else:
                if query is None:
                    return {'_id': {'$gt': last_object_id}}
                else:
                    return {'$and': [{'_id': {'$gt': last_object_id}}, query]}

        cursor = self.col.find(tail_query(), fields)

        while self.tailing:
            if (yield cursor.fetch_next):
                doc = cursor.next_object()
                self.signal_manager.send_catch_log(
                    self.signals['tailed'], data=doc
                )
                last_object_id = doc['_id']
                if self.fetch_delay:
                    yield sleep(self.fetch_delay)
            else:
                yield sleep(1)
                cursor = self.col.find(tail_query(), fields)

    def untail(self):
        self.tailing = False

    def _objectify(self, query):
        ''' Convert ObjectID strings to actual ObjectID in ``query``. '''

        stack = [query]

        while len(stack) > 0:
            d = stack.pop()
            for k, v in d.items():
                if isinstance(v, dict):
                    stack.append(v)
                elif isinstance(v, list):
                    stack.extend(v)
                elif isinstance(v, unicode) and v.startswith(u'ObjectId('):
                    d[k] = ObjectId(v[9:-1])

        return query


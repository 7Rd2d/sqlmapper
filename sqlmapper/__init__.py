# coding: utf8

import MySQLdb
from contextlib import contextmanager
import copy


def Connection(*argv, **kargs):
    @contextmanager
    def mapper(read_commited=False, commit=True):
        connection = MySQLdb.connect(*argv, **kargs)
        cursor = connection.cursor()
        if read_commited:
            cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")

        commited = False
        try:
            yield Mapper(cursor)
            if commit:
                connection.commit()
                commited = True
        finally:
            if not commited:
                connection.rollback()
            cursor.close()

    return mapper


class Mapper(object):
    def __init__(self, cursor=None):
        self.cursor = cursor
        self._table = {}

    def __getattr__(self, name):
        return Table(self, name)

    def show_tables(self):
        self.cursor.execute('SHOW TABLES')
        for row in self.cursor:
            yield row[0]


class Table(object):
    def __init__(self, mapper, table):
        self.mapper = mapper
        self.cursor = mapper.cursor
        self.table = table

    def _build_filter(self, filter):
        if filter is None:
            return None, []
        elif isinstance(filter, dict):
            keys = []
            values = []
            for k, v in filter.items():
                keys.append('`' + k + '`=%s')
                values.append(v)
            sql = ', '.join(keys)
            return sql, values
        elif isinstance(filter, (list, tuple)):
            return filter[0], filter[1:]
        elif isinstance(filter, (str, int)):
            # find by primary key
            key = None
            for column in self.describe():
                if column['primary']:
                    key = column['name']
                    break
            if not key:
                raise ValueError('No primary key')
            return '`{}` = %s'.format(key), [filter]
        else:
            raise NotImplementedError

    def find_one(self, filter=None, columns=None, join=None, for_update=False):
        for row in self.find(filter, limit=1, columns=columns, join=join, for_update=for_update):
            return row

    def find(self, filter=None, columns=None, limit=None, join=None, for_update=False):
        sql = 'SELECT * FROM `{}`'.format(self.table)
        where, values = self._build_filter(filter)
        if where:
            sql += ' WHERE ' + where
        if limit:
            assert isinstance(limit, int)
            sql += ' LIMIT {}'.format(limit)

        self.cursor.execute(sql, tuple(values))

        columns = self.cursor.description
        if self.cursor.rowcount:
            for row in self.cursor:
                d = {}
                for i, value in enumerate(row):
                    col = columns[i]
                    d[col[0]] = value

                yield d

    def update(self, filter=None, update=None):
        up = []
        values = []
        for key, value in update.items():
            up.append('`{}` = %s'.format(key))
            values.append(value)

        sql = 'UPDATE `{}` SET {}'.format(self.table, ', '.join(up))

        where, wvalues = self._build_filter(filter)
        if where:
            sql += ' WHERE ' + where
            values += wvalues

        self.cursor.execute(sql, tuple(values))

    def update_one(self, filter=None, update=None):
        # self.cursor.rowcount
        raise NotImplementedError

    def insert(self, data):
        keys = []
        values = []
        items = []
        for key, value in data.items():
            keys.append('`{}`'.format(key))
            values.append(value)
            items.append('%s')

        sql = 'INSERT INTO `{}` ({}) VALUES ({})'.format(self.table, ', '.join(keys), ', '.join(items))
        self.cursor.execute(sql, tuple(values))
        assert self.cursor.rowcount == 1
        #return self.cursor.lastrowid

    def delete(self):
        raise NotImplementedError

    def create(self):
        raise NotImplementedError

    def drop(self):
        raise NotImplementedError

    def create_index(self):
        raise NotImplementedError

    def has_index(self):
        raise NotImplementedError

    def add_column(self, name, type, not_null=False, default=None, exist_ok=False, primary=False, auto_increment=False):
        values = []
        scolumn = '`{}` {}'.format(name, type)
        if primary:
            not_null = True
        if not_null:
            scolumn += ' NOT NULL'
            if auto_increment:
                scolumn += ' AUTO_INCREMENT'
        if default is not None:
            if not_null or primary:
                raise ValueError('Can''t have default value')
            scolumn += ' DEFAULT %s'
            values.append(default)

        if self.table in self.mapper.show_tables():
            if exist_ok:
                if self.get_column(name):
                    return
            if primary:
                scolumn += ', ADD PRIMARY KEY (`{}`)'.format(name)
            sql = 'ALTER TABLE `{}` ADD COLUMN {}'.format(self.table, scolumn)
        else:
            if primary:
                scolumn += ', PRIMARY KEY (`{}`)'.format(name)
            sql = 'CREATE TABLE `{}` ({}) ENGINE=InnoDB DEFAULT CHARSET=utf8'.format(self.table, scolumn)
        self.cursor.execute(sql, tuple(values))

    def describe(self):
        if self.table not in self.mapper._table:
            result = []
            self.cursor.execute('describe `{}`'.format(self.table))
            for row in self.cursor:
                result.append({
                    'name': row[0],
                    'type': row[1],
                    'null': row[2] == 'YES',
                    'default': row[4],
                    'primary': row[3] == 'PRI',
                    'auto_increment': row[5] == 'auto_increment'
                })
            self.mapper._table[self.table] = result
        return copy.deepcopy(self.mapper._table[self.table])

    def get_column(self, name):
        for column in self.describe():
            if column['name'] == name:
                return column
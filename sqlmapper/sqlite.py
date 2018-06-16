# coding: utf8

from __future__ import absolute_import
import sqlite3
import copy
from .table import Table
from .utils import validate_name, NoValue


class Engine(object):
    def __init__(self, **kw):
        self.conn = sqlite3.connect(kw.get('db') or ':memory:')
        self.cursor = None
        self.local = type('local', (object,), {'tables': {}})()

    def get_cursor(self):
        if not self.cursor:
            self.cursor = self.conn.cursor()
        return self.cursor

    def commit(self):
        self.conn.commit()
    
    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()
        self.conn = None

    def get_columns(self, table):
        result = self.local.tables.get(table)
        if not result:
            result = []
            cursor = self.get_cursor()
            cursor.execute('PRAGMA table_info({})'.format(table))
            for row in cursor:
                result.append({
                    'name': row[1],
                    'type': row[2],
                    'notnull': row[3] == 1,
                    'default': row[4],
                    'primary': row[5] == 1
                })
            self.local.tables[table] = result
        return copy.deepcopy(result)

    def get_table(self, name):
        return SqliteTable(name, self, keyword='?')

    def get_tables(self):
        cursor = self.get_cursor()
        cursor.execute('SELECT name FROM sqlite_master WHERE type = ?', ('table',))
        for row in cursor:
            yield row[0]


sqlite_types = {
    # integer
    'INTEGER': 'INTEGER',
    'INT': 'INTEGER',

    # text
    'TEXT': 'TEXT',
    'VARCHAR': 'TEXT',

    # none
    'NONE': 'NONE',
    'BLOB': 'NONE',

    # real
    'REAL': 'REAL',
    'DOUBLE': 'REAL',
    'FLOAT': 'REAL',

    # numeric
    'NUMERIC': 'NUMERIC',
    'DECIMAL': 'NUMERIC',
    'BOOLEAN': 'NUMERIC',
    'DATE': 'NUMERIC',
    'DATETIME': 'NUMERIC'
}


class SqliteTable(Table):
    def add_column(self, name, type, default=NoValue, exist_ok=False, primary=False, auto_increment=False, not_null=False):
        validate_name(name)

        type = sqlite_types.get(type.upper())
        if not type:
            raise ValueError('Wrong type')

        values = []
        scolumn = '`{}` {}'.format(name, type)

        if primary:
            scolumn += ' PRIMARY KEY'
            if auto_increment:
                scolumn += ' AUTOINCREMENT'
        elif not_null:
            scolumn += ' NOT NULL'

        if default != NoValue:
            if primary:
                raise ValueError('Can''t have default value')
            scolumn += ' DEFAULT ?'
            values.append(default)

        if self.tablename in self.engine.get_tables():
            if exist_ok:
                if self.get_column(name):
                    return
            sql = 'ALTER TABLE `{}` ADD COLUMN {}'.format(self.tablename, scolumn)
        else:
            sql = 'CREATE TABLE {} ({})'.format(self.tablename, scolumn)

        self.cursor.execute(sql, tuple(values))
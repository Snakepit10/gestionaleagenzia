"""
Test database connections
"""
from django.core.management.base import BaseCommand
from django.db import connections
from django.conf import settings
import sys


class Command(BaseCommand):
    help = 'Test database connections'
    
    def handle(self, *args, **options):
        self.stdout.write('🔍 Testing database connections...')
        
        databases = ['default', 'goldbet_db', 'better_db']
        all_ok = True
        
        for db_name in databases:
            try:
                if db_name in settings.DATABASES:
                    conn = connections[db_name]
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 1")
                        result = cursor.fetchone()
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ {db_name}: Connection OK - Result: {result}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'⚠️  {db_name}: Not configured')
                    )
            except Exception as e:
                all_ok = False
                self.stdout.write(
                    self.style.ERROR(f'❌ {db_name}: Connection FAILED - {str(e)}')
                )
        
        if all_ok:
            self.stdout.write(self.style.SUCCESS('🎉 All connections working!'))
        else:
            self.stdout.write(self.style.ERROR('❌ Some connections failed'))
            sys.exit(1)
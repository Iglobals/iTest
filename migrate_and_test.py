import os
from sqlalchemy import text
from app import create_app
from app.extensions import db, mongo_client

def test_and_migrate():
    app = create_app()
    with app.app_context():
        # Test MongoDB Connection
        print("Testing MongoDB connection...")
        try:
            if mongo_client:
                # Issue a ping to test the connection
                mongo_client.admin.command('ping')
                print("MongoDB connection: SUCCESS")
            else:
                print("MongoDB connection: SKIPPED (No URI provided)")
        except Exception as e:
            print(f"MongoDB connection: FAILED - {e}")
            
        # Test PostgreSQL Connection
        print("Testing PostgreSQL connection...")
        try:
            # Issue a simple query
            db.session.execute(text('SELECT 1'))
            print("PostgreSQL connection: SUCCESS")
            
            # Run Migrations
            print("Running PostgreSQL migrations...")
            with open(os.path.join(app.root_path, '..', 'migrations', 'postgres', '001_initial_schema.sql'), 'r') as f:
                sql_script = f.read()
                
            # Execute the script statement by statement or as a whole
            # SQLAlchemy text() might struggle with multiple DDL statements separated by semicolon depending on driver,
            # but psycopg2 usually handles it if executed via connection
            conn = db.engine.raw_connection()
            cursor = conn.cursor()
            cursor.execute(sql_script)
            conn.commit()
            cursor.close()
            conn.close()
            print("PostgreSQL migrations: SUCCESS")
            
        except Exception as e:
            print(f"PostgreSQL operations: FAILED - {e}")

if __name__ == '__main__':
    test_and_migrate()

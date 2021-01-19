from flask import Flask , render_template
import psycorg2 as dbapi2

def create_app():
    app = Flask(__name__)
    
    app.secret_key = b'hunter2'  # Secret key, used for cookies apparently. 
    
    # URL rules go here
    app.add_url_rule("/", view_func=homepage)
    app.add_url_rule("/search",view_func=search_page)
    
    app.add_url_rule("/user/<user_id>",view_func=view_user)
    app.add_url_rule("/printer/<printer_id>",view_func=view_printer)
    app.add_url_rule("/material/<material_id>",view_func=view_material)
    
    app.add_url_rule("/chat/",view_func=view_chat)
    app.add_url_rule("/chat/<other_user_id>",view_func=view_chat)
    app.add_url_rule("/authgroups",view_func=view_authgroups, methods=['GET','POST'])
    app.add_url_rule("/report/",view_func=view_report)
    app.add_url_rule("/report/<report_id>",view_func=view_report)

    app.add_url_rule("/change_user_type", view_func=view_change_user_type, methods=['POST'])
    
    app.add_url_rule("/login", view_func=login)
    app.add_url_rule("/register", view_func=register)
    
    app.add_url_rule("/new_printer", view_func=new_printer)
    app.add_url_rule("/new_material", view_func=new_material)
    app.add_url_rule("/new_review/u/<user_id>", view_func=new_review_user)
    app.add_url_rule("/new_material/p/<printer_id>", view_func=new_review_printer)
    app.add_url_rule("/new_authgroup", view_func=new_authgroup)
    
    
    return app

def connect_to_db():
    global conn
    conn = dbapi2.connect("dbname='foo' user='dbuser' password='mypass'")
    global cursor 
    cursor = conn.cursor()
    return conn


def homepage():
    cursor.execute(""" SELECT _id, printer_name, technology, rating, max_x, max_y, max_z, price FROM printers
                            WHERE available EQUALS TRUE
                            ORDER BY rating DESC NULLS LAST""")
    printers = cursor.fetchall()
    return render_template("homepage.html",user=session['user_id'],printers=printers)

def search_page():
    # TODO search page
    return



def view_user(user_id):
    # Fetch user itself
    cursor.execute("""SELECT _id, account_type, suspended, username, email_address, rating FROM accounts
                        WHERE _id EQUALS %(u_id)s
                    JOIN enum_account_type""", u_id=user_id)
    target_user = cursor.fetch_one()
    if target_user == None:
        abort(404)

    # Fetch any printers they own
    cursor.execute("""SELECT _id, printer_name, technology, max_x, max_y, max_z, available FROM printers
                        WHERE owner_id EQUALS %(o_id)s
                    JOIN enum_printer_technology""", o_id = user_id)
    printers = cursor.fetch_all()
    
    # Fetch any materials they list
    cursor.execute("""(SELECT _id, material_name, material_type FROM materials
                        WHERE _id IN (
                            SELECT material_id FROM lists_material
                                WHERE owner_id EQUALS %(o_id)s
                            )
                        JOIN SELECT * FROM enum_material_type
                    )
                    LEFT OUTER JOIN
                        SELECT owner_id, (material_id AS _id) FROM has_material
                            WHERE owner_id EQUALS %(o_id)s """, o_id = user_id)  
    # TODO [OPTIONAL] There has to be a way to go from owner_id = <o_id | NULL> to available = <True | False> (Maybe VALUES expression will help?)
    materials = cursor.fetchall()
    
    # Fetch any reviews they have on them
    cursor.execute("""SELECT author_id, rating, description, review_date FROM reviews
                        WHERE about_user_id EQUALS %(u_id)s
                    JOIN
                        SELECT (_id AS author_id), (username AS author_username) FROM accounts
                    """)
    reviews = cursor.fetchall()

    
    return render_template("user_page.html",user=session['user'], target_user=target_user, printers=printers, materials=materials, reviews=reviews)

def view_printer(printer_id):
    # Fetch printer itself
    # FEtch its owner
    cursor.execute("""SELECT * FROM printers
                        WHERE _id EQUALS %(p_id)s
                    JOIN
                        SELECT (_id AS owner_id), (username AS owner_username), (rating AS owner_rating) FROM accounts""", p_id = printer_id)
    printer = cursor.fetch_one()

    # Fetch any reviews on it.
    cursor.execute("""SELECT author_id, rating, description, review_date FROM reviews
                        WHERE about_printer_id EQUALS %(p_id)s
                    JOIN
                        SELECT (_id AS author_id), (username AS author_username) FROM accounts
                    """, p_id = printer_id)
    reviews = cursor.fetch_all()

    return render_template("printer_page.html", user=session['user'], printer=target_printer, reviews=reviews)

def view_material(material_id):
    # Fetch material.
    cursor.execute("""SELECT material_name, description, material_type FROM materials
                        WHERE _id EQUALS %(m_id)s """, m_id = material_id)
    material = cursor.fetch_one()
    return render_template("material_page.html", user=session['user'], material=material)

def view_chat(other_user_id=None):
    # TODO Use the auth group permission, damnit
    if session['user_id'] == None:
        abort(503) # This was the "unauthorized access" one, right?
        return
    
    if request.method == 'GET': # Viewing messagelog
        if other_user_id == None:
            # Fetch all chats for the current user
            cursor.execute("""SELECT DISTINCT recipient_id FROM messages
                                WHERE sender_id EQUALS %(s_id)s
                        JOIN
                            SELECT username AS recipient_name, _id AS recipient_id FROM accounts""", s_id = session['user_id'])
            return render_template("chat_list.html", user=session['user'], chats = cursor.fetch_all())

        else:
            # Fetch all messages between the two users
            cursor.execute("""SELECT message_content, message_date FROM messages
                                WHERE (sender_id EQUALS %(s_id)s) AND (recipient_id EQUALS %(r_id)s)
                                ORDER BY message_date DESC""",s_id = session['user'].id, r_id = other_user_id)
            messages = cursor.fetch_all()
            # Fetch some info on the other user maybe?
            cursor.execute("""SELECT _id, username FROM accounts
                                WHERE _id EQUALS %(r_id)s """, r_id = other_user_id)
            
            return render_template("chat_page.html", user=session['user'], messages=messages, recipient=cursor.fetch_one()) 
    else :   # TODO Wrote a new message
        return


def view_authgroups():
    # Check user account type for authorization.
    if session['user'] == None:
        abort(502)
        return
    
    cursor.execute("""SELECT account_type FROM accounts
                        WHERE _id EQUALS %(u_id)
                    JOIN SELECT _id AS account_type, can_edit_account_types FROM account_types""", u_id = session['user'].id)
    user=cursor.fetch_one()
    if (user == None) || (!user[1]):
        abort(502)
        return
    
    # TODO Process the request
    if request.method == 'POST':
        # TODO POST request means an alteration on authgroups was requested.
        return
    else
        # GET rquest means a list of current authgroups
        cursor.execute("""SELECT * FROM account_types
                            JOIN enum_account_type""")
        return render_template("accounttype_list.html",user=session['user'],accounttypes=cursor.fetchall())
    
    return





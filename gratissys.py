from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
import pymysql
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, time, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
import secrets
import qrcode
app = Flask(__name__)
app.secret_key = "yoursecretkey"

# DB Connection
def get_db_connection():
    return pymysql.connect(
        host="127.0.0.1",
        user="root",
        password="",
        database="qr_login_system",
        port=3307,  
        cursorclass=pymysql.cursors.DictCursor
    )

# ------------------ Registration ------------------ #
@app.route("/student-registration")
def student_registration_form():
    return render_template("student-registration.html")

@app.route("/register", methods=["POST"])
def register_student():
    full_name = request.form["full_name"]
    email = request.form["email"]
    username = request.form["username"]
    password = generate_password_hash(request.form["password"])
    student_number = request.form["student_number"]
    year_level = request.form["year_level"]
    program = request.form["program"]
    student_type = request.form["student_type"]
    assigned_duty = request.form["assigned_duty"]

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO users (full_name, email, username, password_hash, student_number,
                               year_level, program, student_type, assigned_duty, role)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'student')
        """, (full_name, email, username, password, student_number,
              year_level, program, student_type, assigned_duty))
        
        conn.commit()
        flash("Student registered successfully!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect("/student-registration")



# ------------------ Login Pages ------------------ #
@app.route('/')
def login():
    return render_template('login.html')

@app.route('/admin-login')
def admin_login():
    return render_template('admin-login.html')

@app.route('/student-login')
def student_login():
    return render_template('student-login.html')

# QR CODE

# Without Restrictions (For demo/testing purposes only)

@app.route('/qr-attendance')
def qr_attendance():
    return render_template('qr_attendance.html')

# @app.route('/validate_qr', methods=['POST'])
# def validate_qr():
#     data = request.get_json()
#     token = data.get('token')

#     if not token:
#         return jsonify({"status": "error", "message": "Invalid QR code."})

#     connection = get_db_connection()
#     cursor = connection.cursor(pymysql.cursors.DictCursor)

#     # Check if QR exists and approved
#     cursor.execute("SELECT * FROM users WHERE qr_token=%s AND status='approved'", (token,))
#     user = cursor.fetchone()

#     if not user:
#         cursor.close()
#         connection.close()
#         return jsonify({"status": "error", "message": "QR code not recognized or not approved."})

#     user_id = user['id']
#     assigned_duty = user.get('assigned_duty', "Unassigned")

#     today = date.today()
#     now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#     # Get latest attendance today
#     cursor.execute("""
#         SELECT * FROM attendance 
#         WHERE user_id=%s AND date=%s 
#         ORDER BY id DESC LIMIT 1
#     """, (user_id, today))
#     last_log = cursor.fetchone()

#     # No record yet today → Time IN
#     if not last_log:
#         cursor.execute("""
#             INSERT INTO attendance (user_id, date, time_in, assigned_duty)
#             VALUES (%s, %s, %s, %s)
#         """, (user_id, today, now, assigned_duty))
#         message = f"{user['full_name']} - Time In Recorded ✅"

#     # If already timed in but not out → Time OUT
#     elif not last_log['time_out']:
#         time_in_dt = datetime.combine(today, datetime.strptime(str(last_log['time_in']), "%H:%M:%S").time())
#         time_out_dt = datetime.now()

#         # Calculate total hours (minus 1 hr lunch break)
#         total_hours = int((time_out_dt - time_in_dt).total_seconds() // 3600) - 1
#         if total_hours < 0:
#             total_hours = 0

#         cursor.execute("""
#             UPDATE attendance
#             SET time_out=%s, total_hours=%s
#             WHERE id=%s
#         """, (now, total_hours, last_log['id']))
#         message = f"{user['full_name']} - Time Out Recorded ⏰ (Total: {total_hours} hrs)"

#     # If already timed out, create new time in for next day/session
#     else:
#         cursor.execute("""
#             INSERT INTO attendance (user_id, date, time_in, assigned_duty)
#             VALUES (%s, %s, %s, %s)
#         """, (user_id, today, now, assigned_duty))
#         message = f"{user['full_name']} - New Time In Recorded ✅"

#     connection.commit()
#     cursor.close()
#     connection.close()

#     return jsonify({"status": "success", "message": message})


# With Restrictions (8-8:15 AM, 5-5:15 PM)

@app.route('/validate_qr', methods=['POST'])
def validate_qr():
    data = request.get_json()
    token = data.get('token')

    if not token:
        return jsonify({"status": "error", "message": "Invalid QR code."})

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Step 1: Validate QR token and approval
        cursor.execute("SELECT * FROM users WHERE qr_token=%s AND status='approved'", (token,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"status": "error", "message": "QR code not recognized or not approved."})

        user_id = user['id']
        student_type = user['student_type']
        today = date.today()
        now = datetime.now().time()

        # Get assigned duty
        assigned_duty = user.get('assigned_duty', "General Services")

        # Check if there's already a record for today
        cursor.execute("SELECT * FROM attendance WHERE user_id=%s AND date=%s", (user_id, today))
        record = cursor.fetchone()

        # Default rule-based time windows
        start_in = time(8, 0)
        cutoff_in = time(8, 15)
        start_out = time(17, 0)
        cutoff_out = time(17, 15)

        # -------------------------
        # ✅ S.T.A.R.S STUDENTS (Flexible Schedule)
        # -------------------------
        if student_type == "S.T.A.R.S":
            if not record:
                # TIME IN (anytime)
                cursor.execute("""
                    INSERT INTO attendance (user_id, date, time_in, assigned_duty)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, today, datetime.now().strftime("%H:%M:%S"), assigned_duty))
                conn.commit()
                message = f"{user['full_name']} - Time In recorded successfully ✅"
            else:
                # TIME OUT (anytime)
                if record['time_out']:
                    return jsonify({"status": "error", "message": "You already timed out today."})

                time_in_dt = datetime.combine(today, record['time_in'])
                time_out_dt = datetime.combine(today, datetime.now().time())

                # Deduct 1 hour if they worked through lunch (12–1)
                lunch_start = datetime.combine(today, time(12, 0))
                lunch_end = datetime.combine(today, time(13, 0))
                total_seconds = (time_out_dt - time_in_dt).total_seconds()
                if time_in_dt < lunch_start < time_out_dt:
                    total_seconds -= 3600

                total_hours = int(total_seconds // 3600)

                cursor.execute("""
                    UPDATE attendance
                    SET time_out=%s, total_hours=%s
                    WHERE id=%s
                """, (datetime.now().strftime("%H:%M:%S"), total_hours, record['id']))

                # Update rendered hours in tbl_schedule
                cursor.execute("""
                    INSERT INTO tbl_schedule (user_id, day, rendered_hours)
                    VALUES (%s, %s, 0)
                    ON DUPLICATE KEY UPDATE rendered_hours = (
                        SELECT IFNULL(SUM(total_hours), 0)
                        FROM attendance WHERE user_id = %s
                    )
                """, (user_id, today.strftime("%A"), user_id))
                conn.commit()

                message = f"{user['full_name']} - Time Out recorded ⏰ | Total Duty Hours: {total_hours} hrs"

            return jsonify({"status": "success", "message": message})

        # -------------------------
        # ⏰ REGULAR STUDENTS (S.A., CS)
        # -------------------------
        if not record:
            # TIME IN
            if not (start_in <= now <= cutoff_in):
                return jsonify({"status": "error", "message": "⏰ You can only time in between 8:00 and 8:15 AM."})

            cursor.execute("""
                INSERT INTO attendance (user_id, date, time_in, assigned_duty)
                VALUES (%s, %s, %s, %s)
            """, (user_id, today, start_in.strftime("%H:%M:%S"), assigned_duty))
            conn.commit()
            message = f"{user['full_name']} - Time In recorded at 8:00 AM ✅"

        else:
            # TIME OUT
            if record['time_out']:
                return jsonify({"status": "error", "message": "You already timed out today."})

            if not (start_out <= now <= cutoff_out):
                return jsonify({"status": "error", "message": "⏰ You can only time out between 5:00 and 5:15 PM."})

            time_in_dt = datetime.combine(today, time(8, 0))
            time_out_dt = datetime.combine(today, time(17, 0))

            total_hours = int((time_out_dt - time_in_dt).total_seconds() // 3600) - 1  # deduct lunch

            cursor.execute("""
                UPDATE attendance
                SET time_out=%s, total_hours=%s
                WHERE id=%s
            """, (start_out.strftime("%H:%M:%S"), total_hours, record['id']))

            cursor.execute("""
                INSERT INTO tbl_schedule (user_id, day, rendered_hours)
                VALUES (%s, %s, 0)
                ON DUPLICATE KEY UPDATE rendered_hours = (
                    SELECT IFNULL(SUM(total_hours), 0)
                    FROM attendance WHERE user_id = %s
                )
            """, (user_id, today.strftime("%A"), user_id))
            conn.commit()

            message = f"{user['full_name']} - Time Out recorded at 5:00 PM ⏰ | Total Duty Hours: {total_hours} hrs"

        return jsonify({"status": "success", "message": message})

    except Exception as e:
        print("Error in validate_qr:", e)
        return jsonify({"status": "error", "message": "⚠️ Server error while processing attendance."})

    finally:
        cursor.close()
        conn.close()


# ------------------ Login Handlers ------------------ #
@app.route('/login-admin', methods=['POST'])
def login_admin():
    username = request.form['username']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=%s AND role='admin'", (username,))
    admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if admin and check_password_hash(admin['password_hash'], password):
        session['user_id'] = admin['id']
        session['role'] = 'admin'
        #flash("Admin login successful", "success")
        return redirect(url_for('admin_dashboard'))
    else:
        flash("Invalid admin credentials", "danger")
        return redirect(url_for('admin_login'))


@app.route('/login-student', methods=['POST'])
def login_student():
    username = request.form['username']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=%s AND role='student'", (username,))
    student = cursor.fetchone()
    cursor.close()
    conn.close()

    if student and check_password_hash(student['password_hash'], password):
        if student['status'] != 'approved':
            flash("Your account is not approved yet.", "warning")
            return redirect(url_for('student_login'))
        session['user_id'] = student['id']
        session['role'] = 'student'
        flash("Student login successful", "success")
        return redirect(url_for('student_dashboard')) 
    else:
        flash("Invalid student credentials", "danger")
        return redirect(url_for('student_login'))

    
# @app.route('/login-student', methods=['POST'])
# def login_student():
#     username = request.form['username']
#     password = request.form['password']

#     conn = get_db_connection()
#     cursor = conn.cursor()
#     cursor.execute("SELECT * FROM users WHERE username=%s AND role='student'", (username,))
#     student = cursor.fetchone()
#     cursor.close()
#     conn.close()

#     if student and check_password_hash(student['password_hash'], password):
#         # Temporarily skip status check
#         session['user_id'] = student['id']
#         session['role'] = 'student'
#         #flash("Student login successful", "success")
#         return redirect(url_for('student_dashboard'))  # Fixed underscore instead of dash
#     else:
#         flash("Invalid student credentials", "danger")
#         return redirect(url_for('student_login'))


# ------------------ Dashboards ------------------ #

@app.route('/admin-dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    
    selected_type = request.args.get('filter')  

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)  

    today = date.today()  

    
    if selected_type:
        cursor.execute("""
            SELECT attendance.*, users.*
            FROM attendance 
            JOIN users ON attendance.user_id = users.id 
            WHERE users.student_type=%s AND attendance.date=%s
            ORDER BY attendance.time_in DESC
        """, (selected_type, today))
    else:
        cursor.execute("""
            SELECT attendance.*, users.*
            FROM attendance 
            JOIN users ON attendance.user_id = users.id 
            WHERE attendance.date=%s
            ORDER BY attendance.time_in DESC
        """, (today,))

    # if selected_type:
    #     cursor.execute("SELECT * FROM attendance JOIN users ON attendance.user_id = users.id WHERE users.student_type=%s", (selected_type,))
    # else:
    #     cursor.execute("SELECT * FROM attendance JOIN users ON attendance.user_id = users.id")

    attendance = cursor.fetchall()

    #
    cursor.execute("""
        SELECT COUNT(*) AS total 
        FROM attendance 
        WHERE time_out IS NULL AND date=%s
    """, (today,))
    students_in = cursor.fetchone()['total']

    
    cursor.execute("""
        SELECT COUNT(*) AS total 
        FROM attendance 
        WHERE time_out IS NOT NULL AND date=%s
    """, (today,))
    students_out = cursor.fetchone()['total']

    cursor.close()
    conn.close()

    return render_template(
        'admin-dashboard.html',
        attendance=attendance,
        students_in=students_in,
        students_out=students_out,
        selected_type=selected_type
    )

@app.route('/api/student_logs/<int:student_id>')
def api_student_logs(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT date, assigned_duty, time_in, time_out, total_hours
        FROM attendance
        WHERE user_id = %s
        ORDER BY date DESC
    """, (student_id,))
    records = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify({"records": records})


@app.route('/view-pending', methods=['GET', 'POST'])
def view_pending():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE role='student' AND status='pending'")
    pending_users = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('view-pending.html', pending_users=pending_users)



@app.route('/approve-student/<int:user_id>')
def approve_student(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    
    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    student = cursor.fetchone()

    if not student:
        flash("Student not found.", "danger")
        cursor.close()
        conn.close()
        return redirect(url_for('view_pending'))
    
    qr_token = secrets.token_hex(16)

    try:
       
        cursor.execute("""
            UPDATE users 
            SET status='approved', qr_token=%s 
            WHERE id=%s
        """, (qr_token, user_id))

        cursor.execute("""
            INSERT INTO status_history (user_id, status, date)
            VALUES (%s, 'approved', CURDATE())
        """, (user_id,))

        conn.commit()

        qr_img = qrcode.make(qr_token)
        img_buffer = BytesIO()
        qr_img.save(img_buffer, format="PNG")
        img_buffer.seek(0)

        
        sender_email = "gratisa1200@gmail.com"
        sender_pass = "zolf herh wytf psmd"
        receiver_email = student["email"]

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg["Subject"] = "🎉 Your Gratis Attendance Account Has Been Approved!"

        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.5;">
            <h2 style="color:#e74c3c;">Hello, {student['full_name']}!</h2>
            <p>Your <strong>Gratis Attendance</strong> account has been <b>approved</b>.</p>
            <p>You can now use the QR code attached below to <b>time in and time out</b>.</p>
            <p style="color:red;"><b>⚠️ Please do not share your QR code with anyone.</b></p>
            <br>
            <p>Best regards,<br><strong>General Services Department</strong></p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, "html"))

        
        qr_image = MIMEImage(img_buffer.read(), _subtype="png")
        qr_image.add_header("Content-Disposition", "attachment", filename="qr_code.png")
        msg.attach(qr_image)

        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender_email, sender_pass)
            smtp.send_message(msg)

        flash(f"{student['full_name']} approved and QR sent successfully via email!", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Student approved but email failed: {str(e)}", "warning")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('view_pending'))


@app.route('/reject-student/<int:user_id>', methods=["POST"])
def reject_student(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # 🧭 Fetch student details
    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    student = cursor.fetchone()

    if not student:
        flash("Student not found.", "danger")
        cursor.close()
        conn.close()
        return redirect(url_for('view_pending'))

    try:
    
        cursor.execute("""
            UPDATE users 
            SET status='rejected' 
            WHERE id=%s
        """, (user_id,))


        cursor.execute("""
            INSERT INTO status_history (user_id, status, date)
            VALUES (%s, 'rejected', CURDATE())
        """, (user_id,))

        conn.commit()


        sender_email = "gratisa1200@gmail.com"
        sender_pass = "zolf herh wytf psmd"
        receiver_email = student["email"]

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg["Subject"] = "Your Gratis Attendance Application Status"

        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.5;">
            <h2 style="color:#e74c3c;">Hello, {student['full_name']}!</h2>
            <p>We appreciate your interest in joining in <strong>General Services Scholars</strong>.</p>
            <p>Unfortunately, your application has been <b>rejected</b> at this time.</p>
            <p>You may contact your coordinator or administrator if you believe this was a mistake.</p>
            <br>
            <p>— Gratis Services Department</p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender_email, sender_pass)
            smtp.send_message(msg)

        flash(f"{student['full_name']} was rejected and notified via email.", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Student rejected but email failed: {str(e)}", "warning")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('view_pending'))



@app.route('/view-logs', methods=["GET"])
def view_logs():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()


    cursor.execute("SELECT id, full_name, student_number FROM users WHERE role='student'")
    students = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("view-logs.html", students=students, student=None, records=None)


@app.route('/view-logs/<int:student_id>', methods=["GET"])
def view_logs_student(student_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id=%s", (student_id,))
    student = cursor.fetchone()

    cursor.execute("""
        SELECT date, assigned_duty, time_in, time_out, total_hours
        FROM attendance
        WHERE user_id=%s
        ORDER BY date ASC
    """, (student_id,))
    records = cursor.fetchall()

    cursor.execute("SELECT id, full_name, student_number FROM users WHERE role='student'")
    students = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("view-logs.html", students=students, student=student, records=records)

@app.route('/view-logs-modal/<int:student_id>', methods=["GET"])
def view_logs_modal(student_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id=%s", (student_id,))
    student = cursor.fetchone()

    
    cursor.execute("""
        SELECT date, assigned_duty, time_in, time_out, total_hours
        FROM attendance
        WHERE user_id=%s
        ORDER BY date ASC
    """, (student_id,))
    records = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("partials/view-logs-modal.html", student=student, records=records)




@app.route('/export-logs/<student_number>')
def export_logs(student_number):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.full_name, u.student_number, u.email, a.date, a.assigned_duty, a.time_in, a.time_out, a.total_hours
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        WHERE u.student_number = %s
        ORDER BY a.date DESC
    """, (student_number,))
    records = cursor.fetchall()


    cursor.execute("SELECT * FROM users WHERE student_number=%s", (student_number,))
    student = cursor.fetchone()

    if student:
        cursor.execute("""
            SELECT date, assigned_duty, time_in, time_out, total_hours
            FROM attendance
            WHERE user_id=%s
            ORDER BY date ASC
        """, (student['id'],))
        Records = cursor.fetchall()

        pdf_data = generate_pdf(student, Records)
        send_pdf_via_email(student, pdf_data)
        
    
    cursor.close()
    conn.close()

    if not records:
        flash("No records found for this student.", "warning")
        return redirect(url_for("view_logs"))
    

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica", 12)

    student_name = records[0]['full_name']
    email = records[0]['email']
    pdf.drawString(50, 750, f"Attendance Report for {student_name} ({student_number})")

    y = 720
    for r in records:
        pdf.drawString(
            50, y,
            f"{r['date']} | Duty: {r['assigned_duty']} | In: {r['time_in']} | Out: {r['time_out']} | Hours: {r['total_hours']}"
        )
        y -= 20
        if y < 50:
            pdf.showPage()
            y = 750

    pdf.save()
    buffer.seek(0)



    flash(f"Attendance report sent to {email}", "success")
    return redirect(url_for("view_logs"))


def generate_pdf(student, records):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)

    
    width, height = letter
    margin_left = 0.75 * inch
    margin_right = 0.75 * inch
    margin_top = 0.75 * inch
    margin_bottom = 0.75 * inch

    content_width = width - (margin_left + margin_right)
    start_y = height - margin_top

    # =============== HEADER SECTION ===============
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawCentredString(width / 2, start_y, "G R A T I S   A T T E N D A N C E   F O R M")

    pdf.setFont("Helvetica", 11)
    pdf.drawString(width - 200, start_y - 25, f"Name: {student['full_name']}")
    pdf.drawString(width - 200, start_y - 40, f"Yr/Course: {student['year_level']} / {student['program']}")
    pdf.drawString(width - 200, start_y - 55, f"Student No.: {student['student_number']}")
    pdf.drawString(width - 200, start_y - 70, f"Contact No.: {student['contact_no']}")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_left, start_y - 25, "Semester: ____________")
    pdf.drawString(margin_left, start_y - 40, "Office/Place of Assignment: ___________________________")

    # =============== LEFT DECLARATION TEXT ===============
    pdf.saveState()
    pdf.translate(margin_left / 2, height / 2)
    pdf.rotate(90)
    pdf.setFont("Helvetica-Oblique", 7)
    pdf.restoreState()

    # =============== TABLE HEADER ===============
    y = start_y - 100
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin_left, y, "Date")
    pdf.drawString(margin_left + 70, y, "Time In")
    pdf.drawString(margin_left + 130, y, "Time Out")
    pdf.drawString(margin_left + 200, y, "Task / Duty Performed")
    pdf.drawString(width - 200, y, "Authorized " \
    "Signature")
    pdf.drawString(width - 80, y, "Hours")
    y -= 10
    pdf.line(margin_left, y, width - margin_right, y)
    y -= 20

    # =============== TABLE CONTENT ===============
    pdf.setFont("Helvetica", 10)
    for record in records:
        if y < margin_bottom + 100: 
            pdf.showPage()
            y = height - margin_top
            pdf.setFont("Helvetica", 10)
        pdf.drawString(margin_left, y, str(record['date']))
        pdf.drawString(margin_left + 70, y, str(record['time_in'] or '--'))
        pdf.drawString(margin_left + 130, y, str(record['time_out'] or '--'))
        pdf.drawString(margin_left + 200, y, str(record['assigned_duty'] or '---'))
        pdf.drawString(width - 80, y, str(record['total_hours'] or '0'))
        y -= 18

    # =============== SIGNATURE FOOTER ===============
    y -= 30
    pdf.line(margin_left, y-40, margin_left + 155, y-40)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin_left + 45, y - 36, student['full_name'])
    pdf.drawString(margin_left , y - 55, "Signature over Printed Name / Date")

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()

def send_pdf_via_email(student, pdf_data):
    from_email = "gratisa1200@gmail.com"
    password = "zolf herh wytf psmd"  

    msg = MIMEMultipart()
    msg['From'] = "gratisa1200@gmail.com"
    msg['To'] = student['email']
    msg['Subject'] = "Your Attendance Report"

    body = f"Hello {student['full_name']},\n\nAttached is your attendance report."
    msg.attach(MIMEText(body, 'plain'))

   
    attachment = MIMEApplication(pdf_data, _subtype="pdf")
    attachment.add_header('Content-Disposition', 'attachment', filename="Attendance_Report.pdf")
    msg.attach(attachment)

    # Send Email
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_email, password) 
        server.send_message(msg)

@app.route('/view-status-history')
def view_status_history():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.full_name, u.student_number, u.program, sh.status, sh.date
        FROM status_history sh
        JOIN users u ON sh.user_id = u.id
        ORDER BY sh.date DESC
    """)
    history = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('view-status-history.html', history=history)


@app.route('/student-dashboard')
def student_dashboard():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('student_login'))

    today = date.today()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id=%s", (session['user_id'],))
    student = cursor.fetchone()
    


    cursor.execute("SELECT * FROM attendance WHERE user_id=%s AND date=%s", (session['user_id'], today))
    today_record = cursor.fetchone()

    cursor.execute("""
        SELECT date, assigned_duty, time_in, time_out, total_hours
        FROM attendance
        WHERE user_id=%s
        ORDER BY date DESC
    """, (session['user_id'],))
    attendance = cursor.fetchall()

    cursor.execute("SELECT * FROM tbl_schedule WHERE user_id=%s", (session['user_id'],))
    schedule = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        'student-dashboard.html',
        student=student,
        today_record=today_record,
        attendance=attendance,
        schedule=schedule,
        current_time=datetime.now().strftime('%H:%M:%S')
    )

# ------------------ Time In/Out without Restrictions ------------------ #

# @app.route('/time_in', methods=['POST'])
# def time_in():
#     if 'user_id' not in session:
#         return redirect(url_for('student_login'))

#     today = date.today()
#     conn = get_db_connection()
#     cursor = conn.cursor()
#         # TEMP: Disable time restriction for testing
#     # now = datetime.now().time()
#     # start_time = time(8, 0)
#     # cutoff_time = time(8, 15)
#     # if not (start_time <= now <= cutoff_time):
#     #     flash("You can only time in between 8:00 and 8:15 AM.", "danger")
#     #     return redirect(url_for('student_dashboard'))

#     # Check if already timed in today
#     cursor.execute("""
#         SELECT * FROM attendance
#         WHERE user_id=%s AND date=%s
#     """, (session['user_id'], today))
#     record = cursor.fetchone()
#     if record:
#         flash("You already timed in today.", "warning")
#         cursor.close()
#         conn.close()
#         return redirect(url_for('student_dashboard'))

    
#     cursor.execute("SELECT assigned_duty FROM users WHERE id=%s", (session['user_id'],))
#     duty_row = cursor.fetchone()
#     assigned_duty = duty_row['assigned_duty'] if duty_row else "Unassigned"

    
#     cursor.execute("""
#         INSERT INTO attendance (user_id, date, time_in, assigned_duty)
#         VALUES (%s, %s, %s, %s)
#     """, (session['user_id'], today, datetime.now().strftime("%H:%M:%S"), assigned_duty))

#     conn.commit()
#     cursor.close()
#     conn.close()

#     flash("Time in recorded successfully!", "success")
#     return redirect(url_for('student_dashboard'))





# def to_time(value):
#     """Convert MySQL TIME (possibly timedelta) to datetime.time."""
#     if isinstance(value, timedelta):
#         total_seconds = value.total_seconds()
#         hours = int(total_seconds // 3600)
#         minutes = int((total_seconds % 3600) // 60)
#         seconds = int(total_seconds % 60)
#         return time(hours, minutes, seconds)
#     return value

# @app.route('/time_out', methods=['POST'])
# def time_out():
#     if 'user_id' not in session:
#         return redirect(url_for('student_login'))

#     user_id = session['user_id']
#     today = date.today()

#     conn = get_db_connection()
#     cursor = conn.cursor()

#     cursor.execute("SELECT * FROM attendance WHERE user_id=%s AND date=%s", (user_id, today))
#     record = cursor.fetchone()

#     if not record or not record['time_in']:
#         flash("You must time in before you can time out.", "danger")
#     elif record['time_out']:
#         flash("You already timed out today.", "warning")
#     else:
#         time_in_dt = datetime.combine(today, to_time(record['time_in']))
#         time_out_dt = datetime.combine(today, datetime.now().time())

#         lunch_start = datetime.combine(today, time(12, 0))
#         lunch_end = datetime.combine(today, time(13, 0))

#         total_seconds = (time_out_dt - time_in_dt).total_seconds()
#         if time_in_dt < lunch_start < time_out_dt:
#             total_seconds -= 3600  # Subtract lunch break

#         total_hours = int(total_seconds // 3600)

#         cursor.execute("""
#             UPDATE attendance
#             SET time_out=%s, total_hours=%s
#             WHERE id=%s
#         """, (datetime.now().strftime("%H:%M:%S"), total_hours, record['id']))
#         conn.commit()

        
#         cursor.execute("SELECT * FROM tbl_schedule WHERE user_id = %s", (user_id,))
#         schedule = cursor.fetchone()
#         if not schedule:
#             cursor.execute("""
#                 INSERT INTO tbl_schedule (user_id, day, rendered_hours)
#                 VALUES (%s, %s, 0)
#             """, (user_id, today.strftime("%A")))   
#             conn.commit()

       
#         cursor.execute("""
#             UPDATE tbl_schedule 
#             SET rendered_hours = (
#                 SELECT IFNULL(SUM(total_hours), 0)
#                 FROM attendance
#                 WHERE user_id = %s
#             )
#             WHERE user_id = %s
#         """, (session['user_id'], session['user_id']))
#         conn.commit()

#         flash("Time out recorded successfully!", "success")

#     cursor.close()
#     conn.close()
#     return redirect(url_for('student_dashboard'))



# # ------------------ Time In/Out with Restrictions ------------------ #


def to_time(value):
    """Convert MySQL TIME (possibly timedelta) to datetime.time."""
    if isinstance(value, timedelta):
        total_seconds = value.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        return time(hours, minutes, seconds)
    return value


@app.route('/time_in', methods=['POST'])
def time_in():
    if 'user_id' not in session:
        return redirect(url_for('student_login'))

    today = date.today()
    now = datetime.now().time()
    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch user details
    cursor.execute("SELECT student_type, assigned_duty FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()

    if not user:
        flash("⚠️ User not found.", "danger")
        cursor.close()
        conn.close()
        return redirect(url_for('student_login'))

    student_type = user['student_type']
    assigned_duty = user['assigned_duty'] or "Unassigned"

    # Restriction for NON-S.T.A.R.S users
    if student_type != "S.T.A.R.S" :
        start_time = time(8, 0)
        cutoff_time = time(8, 15)
        if not (start_time <= now <= cutoff_time):
            flash("⏰ You can only time in between 8:00 and 8:15 AM.", "danger")
            cursor.close()
            conn.close()
            return redirect(url_for('student_dashboard'))

    # Check existing record for today
    cursor.execute("SELECT * FROM attendance WHERE user_id=%s AND date=%s", (user_id, today))
    record = cursor.fetchone()
    if record:
        flash("⚠️ You already timed in today.", "warning")
        cursor.close()
        conn.close()
        return redirect(url_for('student_dashboard'))

    # Determine proper time_in
    fixed_time_in = (
        datetime.now().strftime("%H:%M:%S")  # S.T.A.R.S → any time allowed
        if student_type == "S.T.A.R.S"
        else time(8, 0).strftime("%H:%M:%S")  # Others → fixed at 8:00 AM
    )

    # Insert time-in record
    cursor.execute("""
        INSERT INTO attendance (user_id, date, time_in, assigned_duty)
        VALUES (%s, %s, %s, %s)
    """, (user_id, today, fixed_time_in, assigned_duty))
    conn.commit()

    # Confirmation message
    if student_type == "S.T.A.R.S":
        flash(f"✅ Time in recorded successfully at {fixed_time_in}", "success")
    else:
        flash("✅ Time in recorded as 8:00 AM", "success")

    cursor.close()
    conn.close()
    return redirect(url_for('student_dashboard'))   



@app.route('/time_out', methods=['POST'])
def time_out():
    if 'user_id' not in session:
        return redirect(url_for('student_login'))

    today = date.today()
    now = datetime.now().time()
    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch user details
    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    student_type = user['student_type']

    # Fetch attendance record (safe DATE() comparison)
    cursor.execute("SELECT * FROM attendance WHERE user_id=%s AND DATE(date)=%s", (user_id, today))
    record = cursor.fetchone()

    if not record or not record['time_in']:
        flash("⚠️ You must time in before you can time out.", "danger")
    elif record['time_out']:
        flash("⚠️ You already timed out today.", "warning")
    else:
        # Restrict only if NOT S.T.A.R.S
        if student_type != "S.T.A.R.S":
            start_out = time(17, 0)
            cutoff_out = time(17, 15)
            if not (start_out <= now <= cutoff_out):
                flash("⏰ You can only time out between 5:00 and 5:15 PM.", "danger")
                cursor.close()
                conn.close()
                return redirect(url_for('student_dashboard'))

        # ✅ Convert timedelta to time (in case)
        time_in_value = record['time_in']
        if isinstance(time_in_value, timedelta):
            total_seconds = int(time_in_value.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            time_in_value = time(hours, minutes)

        # Compute total hours
        time_in_dt = datetime.combine(today, time_in_value)
        time_out_dt = datetime.combine(today, datetime.now().time())

        lunch_start = datetime.combine(today, time(12, 0))
        lunch_end = datetime.combine(today, time(13, 0))

        total_seconds = (time_out_dt - time_in_dt).total_seconds()
        if time_in_dt < lunch_start < time_out_dt:
            total_seconds -= 3600  # Deduct 1 hour lunch

        total_hours = int(total_seconds // 3600)

        # ✅ Update attendance
        cursor.execute("""
            UPDATE attendance
            SET time_out=%s, total_hours=%s
            WHERE id=%s
        """, (datetime.now().strftime("%H:%M:%S"), total_hours, record['id']))

        # ✅ Update tbl_schedule
        cursor.execute("SELECT * FROM tbl_schedule WHERE user_id = %s", (user_id,))
        schedule = cursor.fetchone()
        if not schedule:
            cursor.execute("""
                INSERT INTO tbl_schedule (user_id, day, rendered_hours)
                VALUES (%s, %s, 0)
            """, (user_id, today.strftime("%A")))
            conn.commit()

        cursor.execute("""
            UPDATE tbl_schedule 
            SET rendered_hours = (
                SELECT IFNULL(SUM(total_hours), 0)
                FROM attendance
                WHERE user_id = %s
            )
            WHERE user_id = %s
        """, (user_id, user_id))
        conn.commit()

        # ✅ Re-check total rendered hours
        cursor.execute("""
            SELECT u.email, u.full_name, u.student_type, u.created_at, s.rendered_hours
            FROM users u
            JOIN tbl_schedule s ON u.id = s.user_id
            WHERE u.id = %s
        """, (user_id,))
        user_data = cursor.fetchone()

        if user_data:
            rendered_hours = user_data['rendered_hours']
            created_at = user_data['created_at']

            # ⚙️ Convert DATETIME → date
            if isinstance(created_at, datetime):
                created_at = created_at.date()

            email = user_data['email']
            full_name = user_data['full_name']
            student_type = user_data['student_type']

            six_months_after = created_at + timedelta(days=180)

            # 🎯 Completion check (only for SA, Housekeeping, STARS)
            if student_type in ("S.A", "Housekeeping") and rendered_hours >= 60 and date.today() <= six_months_after:
                sender_email = "gratisa1200@gmail.com"
                sender_pass = "zolf herh wytf psmd"

                msg = MIMEMultipart()
                msg["From"] = sender_email
                msg["To"] = email
                msg["Subject"] = "🎉 Congratulations! You’ve Completed Your 60 Hours"

                body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.5;">
                    <h2 style="color:#e74c3c;">Congratulations, {full_name}!</h2>
                    <p>You’ve successfully rendered <b>60 hours</b> of duty under the Gratis Attendance program.</p>
                    <p>Your hard work and dedication are greatly appreciated. Please report to your coordinator for clearance processing.</p>
                    <br>
                    <p>Best regards,<br><strong>General Services Department</strong></p>
                </body>
                </html>
                """
                msg.attach(MIMEText(body, "html"))

                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                    smtp.login(sender_email, sender_pass)
                    smtp.send_message(msg)

                flash("🎉 You have completed 60 hours! Email notification sent successfully!", "success")

        flash(f"✅ Time out recorded. Total hours: {total_hours} hrs", "success")

    cursor.close()
    conn.close()
    return redirect(url_for('student_dashboard'))


# ------------------ Logout ------------------ #
@app.route('/logoutS')
def logoutA():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('admin_login'))

@app.route('/logoutA')
def logoutS():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('student_login'))



if __name__ == '__main__':
    app.run(debug=True)

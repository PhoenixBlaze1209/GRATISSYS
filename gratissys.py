from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import pymysql
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, time, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
app = Flask(__name__)
app.secret_key = "yoursecretkey"

# DB Connection
def get_db_connection():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="",
        database="qr_login_system",
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

    selected_type = request.args.get('filter') # Get selected student type from query params

    conn = get_db_connection()
    cursor = conn.cursor()

    # Filter if type is selected
    if selected_type:
        cursor.execute("SELECT * FROM attendance JOIN users ON attendance.user_id = users.id WHERE users.student_type=%s", (selected_type,))
    else:
        cursor.execute("SELECT * FROM attendance JOIN users ON attendance.user_id = users.id")

    attendance = cursor.fetchall()

    # Count students in/out
    cursor.execute("SELECT COUNT(*) AS total FROM attendance WHERE time_out IS NULL")
    students_in = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM attendance WHERE time_out IS NOT NULL")
    students_out = cursor.fetchone()['total']

    cursor.close()
    conn.close()

    return render_template('admin-dashboard.html',
                           attendance=attendance,
                           students_in=students_in,
                           students_out=students_out,
                           selected_type=selected_type)


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
    cursor.execute("UPDATE users SET status='approved' WHERE id=%s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Student approved successfully!", "success")
    return redirect(url_for('view_pending'))


@app.route('/reject-student/<int:user_id>')
def reject_student(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Student rejected successfully!", "danger")
    return redirect(url_for('view_pending'))


@app.route('/view-logs', methods=["GET"])
def view_logs():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get all students for the sidebar list
    cursor.execute("SELECT id, full_name, student_number FROM users WHERE role='student'LIMIT 9")
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

    # Fetch the selected student
    cursor.execute("SELECT * FROM users WHERE id=%s", (student_id,))
    student = cursor.fetchone()

    # Fetch attendance records
    cursor.execute("""
        SELECT date, assigned_duty, time_in, time_out, total_hours
        FROM attendance
        WHERE user_id=%s
        ORDER BY date ASC
    """, (student_id,))
    records = cursor.fetchall()

    # Get all students for sidebar
    cursor.execute("SELECT id, full_name, student_number FROM users WHERE role='student'LIMIT 9")
    students = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("view-logs.html", students=students, student=student, records=records)




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
    
    # ✅ Create PDF in memory
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

    # ✅ Send via Gmail only
    # send_pdf_via_email(email, student_name, buffer.getvalue())

    flash(f"Attendance report sent to {email}", "success")
    return redirect(url_for("view_logs"))


def generate_pdf(student, records):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    # Student Info at Top
    elements.append(Paragraph(f"<b>Student Name:</b> {student['full_name']}", styles['Normal']))
    elements.append(Paragraph(f"<b>Student ID:</b> {student['student_number']}", styles['Normal']))
    elements.append(Spacer(1, 20))

    # Attendance Table
    data = [["Date", "Assigned Duty", "Time In", "Time Out", "Total Hours"]]
    for r in records:
        data.append([
            str(r['date']),
            r['assigned_duty'] or "--",
            str(r['time_in'] or "--"),
            str(r['time_out'] or "--"),
            str(r['total_hours'] or "--")
        ])

    table = Table(data, colWidths=[80, 100, 80, 80, 80])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.red),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('GRID',(0,0),(-1,-1),0.5,colors.grey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND',(0,1),(-1,-1),colors.whitesmoke)
    ]))
    elements.append(table)
    elements.append(Spacer(1, 50))

    # Signature Footer
    elements.append(Paragraph("<b>Signature:</b> ____________________________", styles['Normal']))

    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

def send_pdf_via_email(student, pdf_data):
    from_email = "gratisa1200@gmail.com"
    password = "zolf herh wytf psmd"  # use Gmail App Password

    msg = MIMEMultipart()
    msg['From'] = "your_email@gmail.com"
    msg['To'] = student['email']
    msg['Subject'] = "Your Attendance Report"

    body = f"Hello {student['full_name']},\n\nAttached is your attendance report."
    msg.attach(MIMEText(body, 'plain'))

    # Attach PDF
    attachment = MIMEApplication(pdf_data, _subtype="pdf")
    attachment.add_header('Content-Disposition', 'attachment', filename="Attendance_Report.pdf")
    msg.attach(attachment)

    # Send Email
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_email, password)  # Use Gmail App Password!
        server.send_message(msg)



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

    cursor.close()
    conn.close()

    return render_template(
        'student-dashboard.html',
        student=student,
        today_record=today_record,
        attendance=attendance,
        current_time=datetime.now().strftime('%H:%M:%S')
    )


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

#     # Fetch assigned_duty from users table
#     cursor.execute("SELECT assigned_duty FROM users WHERE id=%s", (session['user_id'],))
#     duty_row = cursor.fetchone()
#     assigned_duty = duty_row['assigned_duty'] if duty_row else "Unassigned"

#     # Insert new attendance record
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

#     # TEMP: Disable time restriction for testing
#     # now = datetime.now().time()
#     # start_out = time(17, 0)
#     # cutoff_out = time(17, 15)

#     today = date.today()
#     conn = get_db_connection()
#     cursor = conn.cursor()

#     cursor.execute("SELECT * FROM attendance WHERE user_id=%s AND date=%s", (session['user_id'], today))
#     record = cursor.fetchone()

#     if not record or not record['time_in']:
#         flash("You must time in before you can time out.", "danger")
#     elif record['time_out']:
#         flash("You already timed out today.", "warning")
#     else:
#         # Calculate total hours excluding lunch
#         time_in_dt = datetime.combine(today, to_time(record['time_in']))
#         time_out_dt = datetime.combine(today, datetime.now().time())

#         lunch_start = datetime.combine(today, time(12, 0))
#         lunch_end = datetime.combine(today, time(13, 0))

#         total_seconds = (time_out_dt - time_in_dt).total_seconds()

#         if time_in_dt < lunch_start < time_out_dt:
#             total_seconds -= 3600  # subtract 1 hour for lunch

#         total_hours = str(timedelta(seconds=int(total_seconds)))

#         cursor.execute("""
#             UPDATE attendance
#             SET time_out=%s, total_hours=%s
#             WHERE id=%s
#         """, (datetime.now().strftime("%H:%M:%S"), total_hours, record['id']))
#         conn.commit()
#         flash("Time out recorded successfully!", "success")

#     cursor.close()
#     conn.close()
#     return redirect(url_for('student_dashboard'))

# # ------------------ Time In/Out with Restrictions ------------------ #


@app.route('/time_in', methods=['POST'])
def time_in():
    if 'user_id' not in session:
        return redirect(url_for('student_login'))

    today = date.today()
    now = datetime.now().time()
    start_time = time(8, 0)
    cutoff_time = time(8, 15)

    # ⏰ Check if allowed to time in
    if not (start_time <= now <= cutoff_time):
        flash("You can only time in between 8:00 and 8:15 AM.", "danger")
        return redirect(url_for('student_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Prevent multiple time-ins
    cursor.execute("SELECT * FROM attendance WHERE user_id=%s AND date=%s", 
                   (session['user_id'], today))
    record = cursor.fetchone()
    if record:
        flash("You already timed in today.", "warning")
        cursor.close()
        conn.close()
        return redirect(url_for('student_dashboard'))

    # Force store as 08:00:00 regardless of minute
    fixed_time_in = time(8, 0).strftime("%H:%M:%S")

    # Get assigned duty from users table
    cursor.execute("SELECT assigned_duty FROM users WHERE id=%s", (session['user_id'],))
    duty_record = cursor.fetchone()
    assigned_duty = duty_record['assigned_duty'] if duty_record else "Unassigned"

    # Insert record
    cursor.execute("""
        INSERT INTO attendance (user_id, date, time_in, assigned_duty)
        VALUES (%s, %s, %s, %s)
    """, (session['user_id'], today, fixed_time_in, assigned_duty))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Time in recorded as 8:00 AM", "success")
    return redirect(url_for('student_dashboard'))

@app.route('/time_out', methods=['POST'])
def time_out():
    if 'user_id' not in session:
        return redirect(url_for('student_login'))

    today = date.today()
    now = datetime.now().time()
    start_out = time(17, 0)
    cutoff_out = time(17, 15)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM attendance WHERE user_id=%s AND date=%s", 
                   (session['user_id'], today))
    record = cursor.fetchone()

    if not record or not record['time_in']:
        flash("You must time in before you can time out.", "danger")
    elif record['time_out']:
        flash("You already timed out today.", "warning")
    elif not (start_out <= now <= cutoff_out):
        flash("You can only time out between 5:00 and 5:15 PM.", "danger")
    else:
        # Force store as 17:00:00 (5 PM sharp)
        fixed_time_out = time(17, 0)

        # Always time_in is 08:00
        time_in_dt = datetime.combine(today, time(8, 0))
        time_out_dt = datetime.combine(today, fixed_time_out)

        # Subtract 1 hour for lunch
        total_hours = int((time_out_dt - time_in_dt).total_seconds() // 3600) - 1  

        cursor.execute("""
            UPDATE attendance
            SET time_out=%s, total_hours=%s
            WHERE id=%s
        """, (fixed_time_out.strftime("%H:%M:%S"), total_hours, record['id']))
        conn.commit()
        flash(f"Time out recorded. Total duty hours: {total_hours} hrs", "success")

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

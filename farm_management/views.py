from django.shortcuts import render, redirect
from django.db import connection, transaction
from django.contrib import messages
from django.utils.dateparse import parse_date
import datetime


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        with connection.cursor() as cursor:

            cursor.execute(
                "SELECT id, name, type, username FROM user WHERE username = %s AND password = %s",
                [username, password],
            )
            user = cursor.fetchone()

        if user:

            request.session["user_id"] = user[0]
            request.session["user_name"] = user[1]
            request.session["user_type"] = user[2]
            request.session["username"] = user[3]
            return redirect("animal_tracking")
        else:
            messages.error(request, "Invalid Username or Password")

    return render(request, "farm_management/login.html")


def logout_view(request):
    request.session.flush()
    return redirect("login")


# --- FEATURES ---


# FEATURE 1: Animal Tracking & Health (Your "Dashboard")
def animal_tracking(request):
    if "user_id" not in request.session:
        return redirect("login")

    user_id = request.session.get("user_id")
    user_type = request.session.get("user_type")
    username = request.session.get("username")

    with connection.cursor() as cursor:
        if username == "admin" or user_type == "Customer":
            # ADMIN/CUSTOMER VIEW: Show every cow, even those without staff
            query = """
                SELECT c.cattle_id, c.name, c.gender, c.health_status, u.name as caretaker
                FROM cattle c
                LEFT JOIN employee e ON c.employee_id = e.id
                LEFT JOIN user u ON e.user_id = u.id
            """
            cursor.execute(query)
        else:
            # STAFF VIEW: Only show cattle assigned to THIS specific staff member
            query = """
                SELECT c.cattle_id, c.name, c.gender, c.health_status, u.name as caretaker
                FROM cattle c
                INNER JOIN employee e ON c.employee_id = e.id
                INNER JOIN user u ON e.user_id = u.id
                WHERE u.id = %s
            """
            cursor.execute(query, [user_id])

        query = """
            SELECT c.cattle_id, c.name, c.gender, c.health_status, u.name as caretaker, c.breeding_status
            FROM cattle c
            LEFT JOIN employee e ON c.employee_id = e.id
            LEFT JOIN user u ON e.user_id = u.id
        """
        cursor.execute(query)
        row_data = cursor.fetchall()

    return render(request, "farm_management/dashboard.html", {"cattle_list": row_data})


# FEATURE 4: Admin Staff Assignment
def assign_staff(request):

    if "user_id" not in request.session or request.session.get("username") != "admin":
        messages.error(
            request, "Access Denied: Only the Farm Manager can assign staff."
        )
        return redirect("animal_tracking")

    with connection.cursor() as cursor:
        if request.method == "POST":
            cattle_id = request.POST.get("cattle_id")
            employee_id = request.POST.get("employee_id")

            cursor.execute(
                "UPDATE cattle SET employee_id = %s WHERE cattle_id = %s",
                [employee_id, cattle_id],
            )
            return redirect("assign_staff")

        cursor.execute(
            """
            SELECT c.cattle_id, c.name, u.name as caretaker 
            FROM cattle c 
            LEFT JOIN employee e ON c.employee_id = e.id 
            LEFT JOIN user u ON e.user_id = u.id
        """
        )
        cattle_list = cursor.fetchall()

        cursor.execute(
            """
            SELECT e.id, u.name 
            FROM employee e 
            JOIN user u ON e.user_id = u.id
        """
        )
        employee_list = cursor.fetchall()

    return render(
        request,
        "farm_management/assign.html",
        {"cattle_list": cattle_list, "employee_list": employee_list},
    )

#ZR
#FEATURE-3: BREEDING STATUS AND LOG OF THE CATTLES

def breeding_log(request, cattle_id):
    if 'user_id' not in request.session:
        return redirect("login")
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT breeding_date, method, result, expected_delivery, notes
            FROM breeding_log
            WHERE cattle_id = %s
            ORDER BY breeding_date DESC
                       """,[cattle_id])
        logs = cursor.fetchall()
        
        return render(request,
                      "farm_management/breeding.html",
                      {"logs": logs, "cattle_id":cattle_id}
                      )

def add_breeding(request, cattle_id):
    if "user_id" not in request.session:
        return redirect("login")
    
    if request.method == "POST":
        breeding_date = request.POST.get("breeding_date")
        method = request.POST.get("method")
        result = request.POST.get("result")
        expected_delivery = request.POST.get("expected_delivery")
        notes = request.POST.get("notes")

        # Backend validation
        breeding_date_obj = parse_date(breeding_date)
        expected_delivery_obj = parse_date(expected_delivery)

        if expected_delivery_obj < breeding_date_obj:
            messages.error(request, "Expected delivery date cannot be before breeding date.")
            return render(request, "farm_management/add_breeding.html", {"cattle_id": cattle_id})

        with connection.cursor() as cursor:
            # Insert breeding log
            cursor.execute("""
                INSERT INTO breeding_log
                (cattle_id, breeding_date, method, result, expected_delivery, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, [cattle_id, breeding_date, method, result, expected_delivery, notes])

            # Update current breeding status
            cursor.execute("""
                UPDATE cattle
                SET breeding_status = %s
                WHERE cattle_id = %s
            """, [result, cattle_id])

        # Optional: commit to be safe
        transaction.commit()

        # Redirect to dashboard to see updated status
        return redirect("animal_tracking")

    # GET request → show form
    return render(request, "farm_management/add_breeding.html", {"cattle_id": cattle_id})

def task_calendar(request):
    if "user_id" not in request.session:
        return redirect("login")

    user_id = request.session.get("user_id")
    import datetime

    today = datetime.date.today()

    with connection.cursor() as cursor:
        if request.method == "POST":
            task_id = request.POST.get("task_id")
            task_type = request.POST.get("task_type")
            query = f"UPDATE daily_tasks SET {task_type}_done = TRUE WHERE task_id = %s AND task_date = %s"
            cursor.execute(query, [task_id, today])

            # --- NEW SUCCESS LOGIC ---
            # Count total cattle assigned to this staff
            cursor.execute(
                "SELECT COUNT(*) FROM cattle c JOIN employee e ON c.employee_id = e.id JOIN user u ON e.user_id = u.id WHERE u.id = %s",
                [user_id],
            )
            total_cattle = cursor.fetchone()[0]

            # Count how many cattle have all 3 tasks done today
            cursor.execute(
                """
                SELECT COUNT(*) FROM daily_tasks t 
                JOIN cattle c ON t.cattle_id = c.cattle_id
                JOIN employee e ON c.employee_id = e.id
                JOIN user u ON e.user_id = u.id
                WHERE u.id = %s AND t.task_date = %s 
                AND t.feeding_done = 1 AND t.cleaning_done = 1 AND t.medicine_done = 1
            """,
                [user_id, today],
            )
            completed_cattle = cursor.fetchone()[0]

            if total_cattle > 0 and total_cattle == completed_cattle:
                messages.success(
                    request,
                    "🎉 Amazing work! All tasks for all your cattle are officially complete for today!",
                )

            return redirect("task_calendar")

        # Keep your existing FETCH logic here...
        cursor.execute(
            """
            SELECT c.cattle_id, c.name, t.feeding_done, t.cleaning_done, t.medicine_done, t.task_id
            FROM cattle c
            LEFT JOIN daily_tasks t ON c.cattle_id = t.cattle_id AND t.task_date = %s
            JOIN employee e ON c.employee_id = e.id
            JOIN user u ON e.user_id = u.id
            WHERE u.id = %s
        """,
            [today, user_id],
        )
        tasks = cursor.fetchall()

        # Logic to ensure daily rows exist...
        for item in tasks:
            if item[5] is None:
                cursor.execute(
                    "INSERT INTO daily_tasks (cattle_id, task_date) VALUES (%s, %s)",
                    [item[0], today],
                )

        # Re-fetch tasks after insert...
        cursor.execute(
            "SELECT c.cattle_id, c.name, t.feeding_done, t.cleaning_done, t.medicine_done, t.task_id FROM cattle c LEFT JOIN daily_tasks t ON c.cattle_id = t.cattle_id AND t.task_date = %s JOIN employee e ON c.employee_id = e.id JOIN user u ON e.user_id = u.id WHERE u.id = %s",
            [today, user_id],
        )
        tasks = cursor.fetchall()

    return render(
        request, "farm_management/calendar.html", {"tasks": tasks, "today": today}
    )

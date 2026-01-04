from django.shortcuts import render, redirect
from django.db import connection, transaction
from django.contrib import messages
from django.utils.dateparse import parse_date
import datetime


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()


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

    today = datetime.date.today()
    festival_tag = None

    # Festival auto-tagging - ZR
    if today.month == 4:
        festival_tag = "🟣 Eid Sale"
    elif today.month == 10:
        festival_tag = "🟠 Pujo Special"
    elif today.month == 1:
        festival_tag = "🔵 New Year Offer"

    with connection.cursor() as cursor:
        if username == "admin" or user_type == "Customer":
            # ADMIN/CUSTOMER VIEW: Show every cow, even those without staff
            query = """
                SELECT c.cattle_id, c.name, c.gender, c.health_status, u.name as caretaker, c.breeding_status, c.sale_status, c.estimated_value
                FROM cattle c
                LEFT JOIN employee e ON c.employee_id = e.id
                LEFT JOIN user u ON e.user_id = u.id
            """
            cursor.execute(query)
        else:
            # STAFF VIEW: Only show cattle assigned to THIS specific staff member
            query = """
                SELECT c.cattle_id, c.name, c.gender, c.health_status, u.name as caretaker, c.breeding_status, c.sale_status, c.estimated_value
                FROM cattle c
                INNER JOIN employee e ON c.employee_id = e.id
                INNER JOIN user u ON e.user_id = u.id
                WHERE u.id = %s
            """
            cursor.execute(query, [user_id])

        row_data = cursor.fetchall()

    return render(request, "farm_management/dashboard.html", {"cattle_list": row_data, "festival_tag": festival_tag})


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


# ZR
# FEATURE-3: BREEDING STATUS AND LOG OF THE CATTLES


def breeding_log(request, cattle_id):
    if "user_id" not in request.session:
        return redirect("login")

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT breeding_date, method, result, expected_delivery, notes
            FROM breeding_log
            WHERE cattle_id = %s
            ORDER BY breeding_date DESC
        """, [cattle_id])
        columns = [col[0] for col in cursor.description]
        logs = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return render(request, "farm_management/breeding.html", {"logs": logs, "cattle_id": cattle_id})



def add_breeding(request, cattle_id):
    if "user_id" not in request.session:
        return redirect("login")

    # 1. Permission Check: Only Staff and Vet can access this
    allowed_roles = ["Staff", "Vet"]
    if request.session.get("user_type") not in allowed_roles:
        messages.error(
            request, "Access Denied: Only Staff or Vets can modify breeding records."
        )
        return redirect("animal_tracking")

    if request.method == "POST":
        breeding_date = request.POST.get("breeding_date")
        method = request.POST.get("method")
        result = request.POST.get("result")
        expected_delivery = request.POST.get("expected_delivery")
        notes = request.POST.get("notes")

        # Existing validation and SQL logic...
        breeding_date_obj = parse_date(breeding_date)
        expected_delivery_obj = parse_date(expected_delivery)

        if expected_delivery_obj < breeding_date_obj:
            messages.error(
                request, "Expected delivery date cannot be before breeding date."
            )
            return render(
                request, "farm_management/add_breeding.html", {"cattle_id": cattle_id}
            )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO breeding_log
                (cattle_id, breeding_date, method, result, expected_delivery, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
            """,
                [cattle_id, breeding_date, method, result, expected_delivery, notes],
            )

            cursor.execute(
                """
                UPDATE cattle
                SET breeding_status = %s
                WHERE cattle_id = %s
            """,
                [result, cattle_id],
            )

        return redirect("animal_tracking")

    return render(
        request, "farm_management/add_breeding.html", {"cattle_id": cattle_id}
    )


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


#ZR- Feature 2

# FEATURE-2: YIELD & PRODUCTION + SALE STATUS

def production_log(request, cattle_id):
    if "user_id" not in request.session:
        return redirect("login")

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT date_recorded, milk_yield, fat_content, notes
            FROM production
            WHERE cattle_id = %s
            ORDER BY date_recorded DESC
        """, [cattle_id])

        columns = [col[0] for col in cursor.description]
        logs = [dict(zip(columns, row)) for row in cursor.fetchall()]

        # Also get sale info
        cursor.execute("SELECT sale_status, estimated_value FROM cattle WHERE cattle_id=%s", [cattle_id])
        sale_info = cursor.fetchone()
        sale_status = sale_info[0]
        estimated_value = sale_info[1]

    # rename logs -> production_list
    return render(request, "farm_management/production.html", {
        "production_list": logs,  # <--- changed from logs
        "cattle_id": cattle_id,
        "sale_status": sale_status.strip().title(),  # normalize
        "estimated_value": estimated_value
    })



def add_production(request, cattle_id):
    if "user_id" not in request.session:
        return redirect("login")

    allowed_roles = ["Staff", "Vet"]
    if request.session.get("user_type") not in allowed_roles:
        messages.error(request, "Access Denied: Only Staff or Vets can add production records.")
        return redirect("animal_tracking")

    if request.method == "POST":
        date_recorded = request.POST.get("date_recorded")
        milk_yield = request.POST.get("milk_yield")
        fat_content = request.POST.get("fat_content")
        notes = request.POST.get("notes")

        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO production (cattle_id, milk_yield, fat_content, date_recorded, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, [cattle_id, milk_yield, fat_content, date_recorded, notes])

        messages.success(request, "Production record added successfully!")
        return redirect("production_log", cattle_id=cattle_id)

    return render(request, "farm_management/add_production.html", {"cattle_id": cattle_id})


def update_sale_status(request, cattle_id):
    if "user_id" not in request.session:
        return redirect("login")

    allowed_roles = ["Staff", "Vet"]
    if request.session.get("user_type") not in allowed_roles:
        messages.error(request, "Access Denied: Only Staff or Vets can update sale status.")
        return redirect("animal_tracking")

    if request.method == "POST":
        new_status = request.POST.get("sale_status")
        estimated_value = request.POST.get("estimated_value", 0)

        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE cattle
                SET sale_status = %s, estimated_value = %s
                WHERE cattle_id = %s
            """, [new_status, estimated_value, cattle_id])

        messages.success(request, "Sale status updated successfully!")
        return redirect("production_log", cattle_id=cattle_id)

    # if GET request -> then fetch current sell info to pre-fill the form
    with connection.cursor() as cursor:
        cursor.execute("SELECT sale_status, estimated_value FROM cattle WHERE cattle_id=%s", [cattle_id])
        sale_info = cursor.fetchone()
        sale_status = sale_info[0]
        estimated_value = sale_info[1]

    return render(request, "farm_management/update_sale.html", {
        "cattle_id": cattle_id,
        "sale_status": sale_status,
        "estimated_value": estimated_value
    })

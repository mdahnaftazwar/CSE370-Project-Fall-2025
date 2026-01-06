from django.shortcuts import render, redirect
from django.db import connection, transaction
from django.contrib import messages
from django.utils.dateparse import parse_date
import datetime
from decimal import Decimal
from datetime import timedelta, date


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
        if username == "admin" or user_type == "Customer" or user_type == "Vet":

            query = """
                SELECT c.cattle_id, c.name, c.gender, c.health_status, u.name as caretaker, c.breeding_status, c.sale_status, c.estimated_value, c.health_score
                FROM cattle c
                LEFT JOIN employee e ON c.employee_id = e.id
                LEFT JOIN user u ON e.user_id = u.id
            """
            cursor.execute(query)
        else:

            query = """
                SELECT c.cattle_id, c.name, c.gender, c.health_status, u.name as caretaker, c.breeding_status, c.sale_status, c.estimated_value, c.health_score
                FROM cattle c
                INNER JOIN employee e ON c.employee_id = e.id
                INNER JOIN user u ON e.user_id = u.id
                WHERE u.id = %s
            """
            cursor.execute(query, [user_id])

        row_data = cursor.fetchall()

    return render(
        request,
        "farm_management/dashboard.html",
        {"cattle_list": row_data, "festival_tag": festival_tag},
    )


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
            messages.success(request, f"Cattle {cattle_id} successfully reassigned.")
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
            WHERE u.type = 'Staff'
        """
        )
        employee_list = cursor.fetchall()

    return render(
        request,
        "farm_management/assign.html",
        {"cattle_list": cattle_list, "employee_list": employee_list},
    )


def breeding_log(request, cattle_id):
    if "user_id" not in request.session:
        return redirect("login")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT breeding_date, method, result, expected_delivery, notes
            FROM breeding_log
            WHERE cattle_id = %s
            ORDER BY breeding_date DESC
        """,
            [cattle_id],
        )
        columns = [col[0] for col in cursor.description]
        logs = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return render(
        request, "farm_management/breeding.html", {"logs": logs, "cattle_id": cattle_id}
    )


def add_breeding(request, cattle_id):
    if "user_id" not in request.session:
        return redirect("login")

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

    user_type = request.session.get("user_type")
    username = request.session.get("username")

    if user_type != "Staff" or username == "admin":
        messages.error(
            request, "Access Denied: The Task Calendar is only for Staff members."
        )
        return redirect("animal_tracking")

    user_id = request.session.get("user_id")
    import datetime

    today = datetime.date.today()

    with connection.cursor() as cursor:
        if request.method == "POST":
            task_id = request.POST.get("task_id")
            task_type = request.POST.get("task_type")
            query = f"UPDATE daily_tasks SET {task_type}_done = TRUE WHERE task_id = %s AND task_date = %s"
            cursor.execute(query, [task_id, today])

            cursor.execute(
                "SELECT COUNT(*) FROM cattle c JOIN employee e ON c.employee_id = e.id JOIN user u ON e.user_id = u.id WHERE u.id = %s",
                [user_id],
            )
            total_cattle = cursor.fetchone()[0]

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

        for item in tasks:
            if item[5] is None:
                cursor.execute(
                    "INSERT INTO daily_tasks (cattle_id, task_date) VALUES (%s, %s)",
                    [item[0], today],
                )

        cursor.execute(
            "SELECT c.cattle_id, c.name, t.feeding_done, t.cleaning_done, t.medicine_done, t.task_id FROM cattle c LEFT JOIN daily_tasks t ON c.cattle_id = t.cattle_id AND t.task_date = %s JOIN employee e ON c.employee_id = e.id JOIN user u ON e.user_id = u.id WHERE u.id = %s",
            [today, user_id],
        )
        tasks = cursor.fetchall()

    return render(
        request, "farm_management/calendar.html", {"tasks": tasks, "today": today}
    )


def production_log(request, cattle_id):
    if "user_id" not in request.session:
        return redirect("login")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT date_recorded, milk_yield, fat_content, notes
            FROM production
            WHERE cattle_id = %s
            ORDER BY date_recorded DESC
        """,
            [cattle_id],
        )

        columns = [col[0] for col in cursor.description]
        logs = [dict(zip(columns, row)) for row in cursor.fetchall()]

        cursor.execute(
            "SELECT sale_status, estimated_value FROM cattle WHERE cattle_id=%s",
            [cattle_id],
        )
        sale_info = cursor.fetchone()
        sale_status = sale_info[0]
        estimated_value = sale_info[1]

    return render(
        request,
        "farm_management/production.html",
        {
            "production_list": logs,
            "cattle_id": cattle_id,
            "sale_status": sale_status.strip().title(),
            "estimated_value": estimated_value,
        },
    )


def add_production(request, cattle_id):
    if "user_id" not in request.session:
        return redirect("login")

    allowed_roles = ["Staff", "Vet"]
    if request.session.get("user_type") not in allowed_roles:
        messages.error(
            request, "Access Denied: Only Staff or Vets can add production records."
        )
        return redirect("animal_tracking")

    if request.method == "POST":
        date_recorded = request.POST.get("date_recorded")
        milk_yield = request.POST.get("milk_yield")
        fat_content = request.POST.get("fat_content")
        notes = request.POST.get("notes")

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO production (cattle_id, milk_yield, fat_content, date_recorded, notes)
                VALUES (%s, %s, %s, %s, %s)
            """,
                [cattle_id, milk_yield, fat_content, date_recorded, notes],
            )

        messages.success(request, "Production record added successfully!")
        return redirect("production_log", cattle_id=cattle_id)

    return render(
        request, "farm_management/add_production.html", {"cattle_id": cattle_id}
    )


def update_sale_status(request, cattle_id):
    if "user_id" not in request.session:
        return redirect("login")

    allowed_roles = ["Staff", "Vet"]
    if request.session.get("user_type") not in allowed_roles:
        messages.error(
            request, "Access Denied: Only Staff or Vets can update sale status."
        )
        return redirect("animal_tracking")

    if request.method == "POST":
        new_status = request.POST.get("sale_status")
        estimated_value = request.POST.get("estimated_value", 0)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE cattle
                SET sale_status = %s, estimated_value = %s
                WHERE cattle_id = %s
            """,
                [new_status, estimated_value, cattle_id],
            )

        messages.success(request, "Sale status updated successfully!")
        return redirect("production_log", cattle_id=cattle_id)

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sale_status, estimated_value FROM cattle WHERE cattle_id=%s",
            [cattle_id],
        )
        sale_info = cursor.fetchone()
        sale_status = sale_info[0]
        estimated_value = sale_info[1]

    return render(
        request,
        "farm_management/update_sale.html",
        {
            "cattle_id": cattle_id,
            "sale_status": sale_status,
            "estimated_value": estimated_value,
        },
    )


def manage_salaries(request):
    if request.session.get("username") != "admin":
        messages.error(request, "Access Denied.")
        return redirect("animal_tracking")

    with connection.cursor() as cursor:
        if request.method == "POST":
            emp_id = request.POST.get("employee_id")

            base_salary = Decimal(request.POST.get("salary"))
            new_rating = request.POST.get("rating")

            final_salary = base_salary

            if new_rating == "Excellent":

                final_salary = base_salary * Decimal("1.10")
                messages.success(
                    request, f"Salary increased by 10% for Excellent performance!"
                )
            elif new_rating == "Poor":

                final_salary = base_salary * Decimal("0.90")
                messages.warning(
                    request, f"Salary deducted by 10% due to Poor performance."
                )

            cursor.execute(
                """
                UPDATE employee_performance 
                SET current_salary = %s, rating = %s 
                WHERE employee_id = %s
            """,
                [final_salary, new_rating, emp_id],
            )

            cursor.execute(
                "UPDATE employee SET salary = %s WHERE id = %s", [final_salary, emp_id]
            )

            return redirect("manage_salaries")

        cursor.execute(
            """
            SELECT e.id, u.name, u.type, p.current_salary, p.rating 
            FROM employee e
            JOIN user u ON e.user_id = u.id
            LEFT JOIN employee_performance p ON e.id = p.employee_id
        """
        )
        employee_data = cursor.fetchall()

    return render(
        request, "farm_management/salaries.html", {"employees": employee_data}
    )


def manage_feed(request):

    if request.session.get("username") != "admin":
        messages.error(request, "Access Denied: Admin only.")
        return redirect("animal_tracking")

    today = date.today()

    with connection.cursor() as cursor:
        if request.method == "POST":
            feed_type = request.POST.get("feed_type")
            qty_input = request.POST.get("quantity")

            try:
                qty_change = Decimal(qty_input)
            except (TypeError, ValueError):
                messages.error(request, "Invalid quantity entered.")
                return redirect("manage_feed")

            action = request.POST.get("action")

            days_valid = {
                "Green Grass": 2,
                "Silage": 365,
                "Hay": 365,
                "Supplements": 180,
            }
            expiry = today + timedelta(days=days_valid.get(feed_type, 30))

            if action == "add":

                cursor.execute(
                    """
                    INSERT INTO feed_inventory (feed_type, quantity_kg, expiration_date)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                    quantity_kg = quantity_kg + %s, expiration_date = %s
                """,
                    [feed_type, qty_change, expiry, qty_change, expiry],
                )

                cursor.execute(
                    "INSERT INTO feed_log (feed_type, action_type, quantity_kg) VALUES (%s, 'Added', %s)",
                    [feed_type, qty_change],
                )

            elif action == "remove":

                cursor.execute(
                    "SELECT quantity_kg FROM feed_inventory WHERE feed_type = %s",
                    [feed_type],
                )
                current_stock = cursor.fetchone()

                if current_stock and current_stock[0] >= qty_change:
                    cursor.execute(
                        "UPDATE feed_inventory SET quantity_kg = quantity_kg - %s WHERE feed_type = %s",
                        [qty_change, feed_type],
                    )
                    cursor.execute(
                        "INSERT INTO feed_log (feed_type, action_type, quantity_kg) VALUES (%s, 'Removed', %s)",
                        [feed_type, qty_change],
                    )
                else:
                    messages.error(
                        request,
                        f"Not enough {feed_type} in stock to remove {qty_change}kg.",
                    )
                    return redirect("manage_feed")

            messages.success(request, f"Inventory updated for {feed_type}")
            return redirect("manage_feed")

        cursor.execute(
            "SELECT feed_type, quantity_kg, expiration_date FROM feed_inventory"
        )
        inventory = cursor.fetchall()

        cursor.execute(
            "SELECT feed_type, action_type, quantity_kg, log_date FROM feed_log ORDER BY log_date DESC LIMIT 10"
        )
        logs = cursor.fetchall()

    return render(
        request,
        "farm_management/feed.html",
        {"inventory": inventory, "logs": logs, "today": today},
    )


def update_health(request, cattle_id):
    if request.session.get("user_type") != "Vet":
        messages.error(request, "Access Denied: Only a Vet can update health scores.")
        return redirect("animal_tracking")

    if request.method == "POST":
        score = int(request.POST.get("health_score"))

        if score < 30:
            status = "Severely Sick"
        elif score < 50:
            status = "Sick"
        elif score <= 80:
            status = "Healthy"
        else:
            status = "Excellent"

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE cattle 
                SET health_score = %s, health_status = %s 
                WHERE cattle_id = %s
            """,
                [score, status, cattle_id],
            )

        messages.success(request, f"Health record for {cattle_id} updated to {status}.")
        return redirect("animal_tracking")

    return render(
        request, "farm_management/update_health.html", {"cattle_id": cattle_id}
    )

from django.shortcuts import render, redirect
from django.db import connection
from django.contrib import messages


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        with connection.cursor() as cursor:

            cursor.execute(
                "SELECT id, name, type FROM user WHERE username = %s AND password = %s",
                [username, password],
            )
            user = cursor.fetchone()

        if user:

            request.session["user_id"] = user[0]
            request.session["user_name"] = user[1]
            request.session["user_type"] = user[2]
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

    with connection.cursor() as cursor:

        query = """
            SELECT c.cattle_id, c.name, c.gender, c.health_status, u.name as caretaker
            FROM cattle c
            LEFT JOIN employee e ON c.employee_id = e.id
            LEFT JOIN user u ON e.user_id = u.id
        """
        cursor.execute(query)
        row_data = cursor.fetchall()

    return render(request, "farm_management/dashboard.html", {"cattle_list": row_data})


# FEATURE 4: Admin Staff Assignment
def assign_staff(request):

    if "user_id" not in request.session or request.session.get("user_type") != "Staff":
        return redirect("login")

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

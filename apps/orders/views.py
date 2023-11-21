from datetime import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import get_template
from django.urls import reverse, reverse_lazy
from weasyprint import HTML

from apps.inventory.models import Menu
from apps.orders.models import (Order, OrderItem, TemporaryCustomerOrderItem,
                                TemporaryOrderItem)
from apps.reports.models import SalesReport
from apps.students.models import Student, StudentWallet, WalletRechargeLog

from .utils import determin_meal_time

date_today = datetime.now().date()
# Create your views here.


def generate_receipt_pdf(request, order_id=None):
    # Fetch order data and generate receipt data

    order = Order.objects.get(id=order_id)

    template = get_template('receipt_template.html')
    html_content = template.render({'order': order})

    pdf_file = HTML(string=html_content).write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=receipt_{order_id}.pdf'

    return response


@login_required(login_url="/users/login/")
def orders(request):
    user = request.user
    orders = Order.objects.all().order_by("-created")

    if not user.is_superuser:
        orders = Order.objects.filter(served_by=user).order_by("-created")

    if request.method == "POST":
        registration_number = request.POST.get("reg_number")
        orders = Order.objects.filter(
            Q(student__registration_number__icontains=registration_number))

    paginator = Paginator(orders, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "orders": orders,
        "page_obj": page_obj,
    }
    return render(request, "orders/orders.html", context)


@login_required(login_url="/users/login/")
def edit_order(request):
    if request.method == "POST":
        order_id = request.POST.get("order_id")
        status = request.POST.get("status")
        meal_time = request.POST.get("meal_time")

        order = Order.objects.get(id=order_id)
        order.status = status
        order.meal_time = meal_time
        order.save()
        return redirect("orders")

    return render(request, "orders/edit_order.html")


@login_required(login_url="/users/login/")
def delete_order(request):
    if request.method == "POST":
        order_id = request.POST.get("order_id")
        order = Order.objects.get(id=order_id)
        order.delete()
        return redirect("orders")

    return render(request, "orders/delete_order.html")


@login_required(login_url="/users/login/")
def pos_home(request):
    students = Student.objects.none()
    students_list = Student.objects.all()
    quotas_generated = True

    boarding_student_wallets = StudentWallet.objects.filter(
        student__student_type="Boarder", student__status="Active").exclude(modified__date=date_today)

    print(f"Quotas Not Generated: {boarding_student_wallets.count()}")

    if boarding_student_wallets.count() >= 1:
        quotas_generated = False

    if request.method == "POST":
        id_number = request.POST.get("id_number")
        students = Student.objects.filter(Q(user__id_number__icontains=id_number) | Q(
            registration_number__icontains=id_number))

        if students.count() == 1:
            first_student = students.first()
            print(f"Student: {first_student.registration_number}")
            return redirect(f"/orders/place-order/{first_student.id}/")

    context = {
        "students": students,
        "quotas_generated": quotas_generated,
        "students_list": students_list
    }

    return render(request, "orders/pos_home.html", context)


@login_required(login_url="/users/login/")
def pos(request):
    
    students = Student.objects.all()
    menus = Menu.objects.none()  # filter(added_to_cart=False)
    selected_student = request.session.get('selected_student')

    if request.method == "POST":
            reg_number = request.POST.get('reg_number')
            print(f"Student Reg. Number: {reg_number}")

            try:
                student = Student.objects.get(registration_number=reg_number)
                request.session['selected_student'] = {
                    'id': student.id,
                    'name': f'{student.user.first_name} {student.user.last_name}',
                    'registration_number': student.registration_number,
                    'wallet_balance': str(student.wallet_balance),
                }
                
                print(f"Selected Student: {student.user.first_name} {student.user.last_name}")
                return redirect('place-order')
            except Student.DoesNotExist:
                # Handle the case when the student is not found
                pass

    if request.method == "POST":
        item = request.POST.get("item")
        print(f"Searched Item: {item}")
        menus = Menu.objects.filter(Q(item__icontains=item)).filter(quantity__gt=0)
        print(f"Found Menu Items: {menus}")

    print(f"Select Student: {selected_student}")

    context = {
        "selected_student": selected_student,
        "student": None,
        "menus": menus,
        "students": students
    }

    
    if selected_student:
        student = Student.objects.filter(
            id=selected_student['id']
        ).first()

        items = TemporaryOrderItem.objects.filter(student=student)
        order_value = sum(TemporaryOrderItem.objects.filter(
            student=student).values_list("price", flat=True))

        menus = Menu.objects.exclude(
            id__in=list(TemporaryOrderItem.objects.filter(
                student=student).values_list('menu_item_id', flat=True))
        ).filter(quantity__gt=0)

        extra_amount = order_value - student.studentwallet.balance

        paginator = Paginator(menus, 12)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        context = {
            "student": student,
            "menus": menus,
            "items": items,
            "page_obj": page_obj,
            "order_value": order_value,
            "extra_amount": extra_amount,
            "students": students,
            "selected_student": selected_student
        }
    return render(request, "orders/pos.html", context)


@login_required(login_url="/users/login/")
@transaction.atomic
def confirm_order(request, student_id=None, *args, **kwargs):
    user = request.user
    student = Student.objects.get(id=student_id)
    meal_time = determin_meal_time()

    order_value = sum(TemporaryOrderItem.objects.filter(
        student=student).values_list("price", flat=True))

    order = Order.objects.create(
        student=student,
        status="Processed",
        total_cost=order_value,
        meal_time=meal_time,
        served_by=user
    )

    items = TemporaryOrderItem.objects.all()

    order_items_list = []
    for order_item in items:
        order_items_list.append(OrderItem(
            order=order,
            item=order_item.menu_item,
            quantity=order_item.quantity,
            price=order_item.price
        ))

    order_items = OrderItem.objects.bulk_create(order_items_list)

    for order_item in order_items:
        menu_item = Menu.objects.get(id=order_item.item.id)
        menu_item.quantity -= order_item.quantity
        menu_item.save()

    student.studentwallet.balance -= order_value
    student.studentwallet.total_spend_today += order_value
    student.studentwallet.save()

    wallet_payment = SalesReport.objects.create(
        order=order,
        payment_method="Wallet",
        amount=order_value
    )

    Menu.objects.update(added_to_cart=False)
    TemporaryOrderItem.objects.all().delete()
    del request.session['selected_student']
    return redirect(f"/orders/print-order/{order.id}/")


@login_required(login_url="/users/login/")
@transaction.atomic
def confirm_overpaid_order(request):
    user = request.user

    if request.method == "POST":
        recharge_method = request.POST.get("recharge_method")
        amount = Decimal(request.POST.get("amount"))
        student_id = int(request.POST.get("student_id"))

        student = Student.objects.get(id=student_id)

        recharge_log = WalletRechargeLog.objects.create(
            student=student,
            wallet=student.studentwallet,
            recharge_method=recharge_method,
            amount_recharged=amount
        )

        student.studentwallet.balance += amount
        student.studentwallet.save()


        meal_time = determin_meal_time()

        order_value = sum(TemporaryOrderItem.objects.filter(
            student=student).values_list("price", flat=True))

        order = Order.objects.create(
            student=student,
            status="Processed",
            total_cost=order_value,
            meal_time=meal_time,
            served_by=user
        )

        items = TemporaryOrderItem.objects.all()

        order_items_list = []
        for order_item in items:
            order_items_list.append(OrderItem(
                order=order,
                item=order_item.menu_item,
                quantity=order_item.quantity,
                price=order_item.price
            ))

        order_items = OrderItem.objects.bulk_create(order_items_list)

        for order_item in order_items:
            menu_item = Menu.objects.get(id=order_item.item.id)
            menu_item.quantity -= order_item.quantity
            menu_item.save()

        student.studentwallet.balance -= order_value
        student.studentwallet.total_spend_today += order_value
        student.studentwallet.save()

        if recharge_method == "Mpesa":
            wallet_payment = SalesReport.objects.create(
                order=order,
                payment_method="Wallet",
                amount=order_value-amount
            )
            mpesa_payment = SalesReport.objects.create(
                order=order,
                payment_method="Mpesa",
                amount=amount
            )
        elif recharge_method == "Cash":
            wallet_payment = SalesReport.objects.create(
                order=order,
                payment_method="Wallet",
                amount=order_value-amount
            )
            cash_payment = SalesReport.objects.create(
                order=order,
                payment_method="Cash",
                amount=amount
            )

        Menu.objects.update(added_to_cart=False)
        TemporaryOrderItem.objects.all().delete()
        return redirect(f"/orders/print-order/{order.id}/")


@login_required(login_url="/users/login/")
def add_to_cart(request, menu_id=None, student_id=None):
    menu_item = Menu.objects.get(id=menu_id)

    total_price = menu_item.price * 1
    TemporaryOrderItem.objects.create(
        student_id=student_id,
        menu_item=menu_item,
        quantity=1,
        price=total_price
    )
    return redirect(f"/orders/place-order/")


@login_required(login_url="/users/login/")
def edit_order_item(request):
    if request.method == "POST":
        student_id = request.POST.get("student_id")
        order_item_id = request.POST.get("order_item_id")
        quantity = Decimal(request.POST.get("quantity"))

        item = TemporaryOrderItem.objects.get(id=order_item_id)
        item.quantity = quantity
        item.price = quantity * item.menu_item.price
        item.save()
        return redirect(f"/orders/place-order/{student_id}/")
    return render(request, "orders/edit_order_item.html")


@login_required(login_url="/users/login/")
def remove_from_cart(request, item_id=None):
    item = TemporaryOrderItem.objects.get(id=item_id)
    menu_item = Menu.objects.get(id=item.menu_item.id)
    menu_item.added_to_cart = False
    menu_item.save()

    student_id = item.student.id
    item.delete()
    return redirect(f"/orders/place-order/")


@login_required(login_url="/users/login/")
def print_order_receipt(request, order_id=None):
    order = Order.objects.get(id=order_id)
    order_items = order.orderitems.all()

    context = {
        "order": order,
        "order_items": order_items
    }
    if request.session.get('selected_student'):
        del request.session['selected_student']
    return render(request, "orders/receipt.html", context)


@login_required(login_url="/users/login/")
def increase_order_item_quantity(request, item_id=None, student_id=None):
    item = TemporaryOrderItem.objects.get(id=item_id)
    item.quantity += 1
    item.price += item.menu_item.price
    item.save()
    print(f"Student ID: {student_id}")
    return redirect(f"/orders/place-order/")


@login_required(login_url="/users/login/")
def decrease_order_item_quantity(request, item_id=None, student_id=None):
    item = TemporaryOrderItem.objects.get(id=item_id)
    if item.quantity == 0:
        item.quantity = 0
        item.save()
    else:
        item.quantity -= 1
        item.price -= item.menu_item.price
        item.save()
    return redirect(f"/orders/place-order/")


@login_required(login_url="/users/login/")
def clear_order_items(request, student_id=None):
    items = TemporaryOrderItem.objects.filter(student_id=student_id)
    if items:
        items.delete()
        print(items)
    return redirect(f"/orders/place-order/")

########################## Walk In Customer Logic ######################

"""
@login_required(login_url="/users/login/")
def clear_shopping_cart(request):
    items = TemporaryCustomerOrderItem.objects.all().delete()
    return redirect("customer-order")


@login_required(login_url="/users/login/")
def add_cart_items(request, item_id=None):
    menu_item = Menu.objects.get(id=item_id)

    item = TemporaryCustomerOrderItem.objects.create(
        menu_item=menu_item,
        quantity=1,
        price=menu_item.price
    )

    return redirect("customer-order")


@login_required(login_url="/users/login/")
def delete_cart_item(request, item_id=None):
    item = TemporaryCustomerOrderItem.objects.get(id=item_id)
    item.delete()
    return redirect("customer-order")


@login_required(login_url="/users/login/")
def customer_order(request):
    students = Student.objects.all()
    cart_items = TemporaryCustomerOrderItem.objects.all()

    selected_student = request.session.get('selected_student')

    print("This view was reached!!")
    print(f"Request Method: {request.method}")

    if request.method == 'POST':
        reg_number = request.POST.get('reg_number')
        print(f"Student Reg. Number: {reg_number}")

        try:
            student = Student.objects.get(registration_number=reg_number)
            request.session['selected_student'] = {
                'id': student.id,
                'name': f'{student.user.first_name} {student.user.last_name}',
                'registration_number': student.registration_number,
                'wallet_balance': str(student.wallet_balance),
            }
            selected_student = request.session.get('selected_student')
            print(f"Selected Student: {student.user.first_name} {student.user.last_name}")
            return redirect('customer-order')
        except Student.DoesNotExist:
            # Handle the case when the student is not found
            pass

    items_added = False
    if cart_items.count() >= 1:
        items_added = True

    menus = Menu.objects.exclude(
        id__in=TemporaryCustomerOrderItem.objects.values_list(
            "menu_item_id", flat=True)
    )

    order_value = sum(
        list(TemporaryCustomerOrderItem.objects.values_list("price", flat=True)))

    paginator = Paginator(menus, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "menus": menus,
        "page_obj": page_obj,
        "cart_items": cart_items,
        "order_value": order_value,
        "items_added": items_added,
        "students": students,
        "selected_student": selected_student
    }
    return render(request, "orders/customer_order.html", context)


@login_required(login_url="/users/login/")
@transaction.atomic
def place_customer_mpesa_order(request):
    user = request.user
    meal_time = determin_meal_time()

    order_value = sum(
        list(TemporaryCustomerOrderItem.objects.values_list("price", flat=True)))

    order = Order.objects.create(
        status="Processed",
        total_cost=order_value,
        meal_time=meal_time,
        served_by=user
    )

    items = TemporaryCustomerOrderItem.objects.all()

    order_items_list = []
    for order_item in items:
        order_items_list.append(OrderItem(
            order=order,
            item=order_item.menu_item,
            quantity=order_item.quantity,
            price=order_item.price
        ))

    order_items = OrderItem.objects.bulk_create(order_items_list)

    for order_item in order_items:
        menu_item = Menu.objects.get(id=order_item.item.id)
        menu_item.quantity -= order_item.quantity
        menu_item.save()

    sales_report_log = SalesReport.objects.create(
        order=order,
        payment_method="Mpesa",
        amount=order_value
    )

    TemporaryCustomerOrderItem.objects.all().delete()
    request.session.flush()
    return redirect(f"/orders/print-order/{order.id}/")


@login_required(login_url="/users/login/")
@transaction.atomic
def place_customer_cash_order(request):
    user = request.user
    meal_time = determin_meal_time()

    order_value = sum(
        list(TemporaryCustomerOrderItem.objects.values_list("price", flat=True)))

    order = Order.objects.create(
        status="Processed",
        total_cost=order_value,
        meal_time=meal_time,
        served_by=user
    )

    items = TemporaryCustomerOrderItem.objects.all()

    order_items_list = []
    for order_item in items:
        order_items_list.append(OrderItem(
            order=order,
            item=order_item.menu_item,
            quantity=order_item.quantity,
            price=order_item.price
        ))

    order_items = OrderItem.objects.bulk_create(order_items_list)

    for order_item in order_items:
        menu_item = Menu.objects.get(id=order_item.item.id)
        menu_item.quantity -= order_item.quantity
        menu_item.save()
    
    sales_report_log = SalesReport.objects.create(
        order=order,
        payment_method="Cash",
        amount=order_value
    )

    TemporaryCustomerOrderItem.objects.all().delete()

    return redirect(f"/orders/print-order/{order.id}/")

@login_required(login_url="/users/login/")
def increase_item_quantity(request, item_id=None):
    item = TemporaryCustomerOrderItem.objects.get(id=item_id)
    item.quantity += 1
    item.price += item.menu_item.price
    item.save()
    return redirect("customer-order")


@login_required(login_url="/users/login/")
def decrease_item_quantity(request, item_id=None):
    item = TemporaryCustomerOrderItem.objects.get(id=item_id)

    if item.quantity == 0:
        item.quantity = 0
    else:
        item.quantity -= 1
        item.price -= item.menu_item.price
        item.save()
    return redirect("customer-order")
"""


@login_required(login_url="/users/login/")
def recharge_student_wallet_at_order(request):
    if request.method == "POST":
        reg_number = request.POST.get("reg_number")
        recharge_method = request.POST.get("recharge_method")

        student = Student.objects.filter(
            Q(registration_number=reg_number) | Q(user__id_number=reg_number)).first()

        amount = Decimal(request.POST.get("amount"))

        wallet = student.studentwallet
        wallet.balance += amount
        wallet.save()

        recharge_log = WalletRechargeLog.objects.create(
            student=student,
            wallet=wallet,
            recharge_method=recharge_method,
            amount_recharged=amount
        )
        del request.session['selected_student']
        return redirect(f"/orders/place-order/{student.id}")

    return render(request, "modals/request_recharge.html")


def void_customer_order(request):
    if request.method == "POST":
        order_id = int(request.POST.get("order_id"))

        order = Order.objects.get(id=order_id)
        order.status = "Nullified"

        sales_reports = SalesReport.objects.filter(order=order)

        for sale_report in sales_reports:
            if sale_report.payment_method in ["Mpesa", "Cash"]:
                sale_report.amount = 0
                sale_report.save()

            elif sale_report.payment_method == "Wallet":
                sale_report_amount = sale_report.amount
                student = sale_report.order.student
                student_wallet = student.studentwallet
                student_wallet.balance += sale_report_amount
                student_wallet.total_spend_today -= sale_report_amount
                student_wallet.save()

                sale_report.amount = 0
                sale_report.save()

        order.save()

        return redirect("orders")
    return render(request, "orders/void_order.html")
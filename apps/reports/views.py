import csv
from datetime import datetime, timedelta
from django.db.models import Sum

from django.shortcuts import render
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseRedirect

date_today = datetime.now().date()
# Create your views here.
from apps.reports.models import SalesReport, DailySalesReport


def today_sales_report(request):
    sales_today = SalesReport.objects.filter(created__date=date_today, sold_or_spoiled="Sold").order_by("-created")
    paginator = Paginator(sales_today, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    
    report_data = list(
        DailySalesReport.objects.filter(created__date=date_today).values('payment_method')
        .annotate(total_sales_amount=Sum('amount'))
        .order_by('payment_method')
    )

    sales_total = sum(list(SalesReport.objects.filter(
        created__date=date_today, sold_or_spoiled="Sold").values_list('amount', flat=True)))

    if request.method == "POST":
        action_type = request.POST.get("action_type")
        print(f"Action Type: {action_type}")
        
        if action_type == "item_sales":
            response = HttpResponse(content_type='text/csv')
            file_name =  f'attachment; filename="Sales Report - {date_today}.csv"'    
            response['Content-Disposition'] = file_name
            writer = csv.writer(response)
            writer.writerow(['ID', 'Sales Date', 'Item Sold','Sold or Spoiled', 'Quantity Sold', 'Unit Price', 'Amount']) 
            checkins = sales_today.values_list('id', 'created__date','item','sold_or_spoiled', 'quantity', 'unit_price', 'amount')       

            for checkin in checkins:
                writer.writerow(checkin)
            writer.writerow(["", "", "", "", "", "", ""])
            writer.writerow(["Total Sales", "", "", "", "", "", sales_total])
            return response
        elif action_type == "overall_sales":
            csv_data = [['Report Date', 'Payment Method', 'Total Sales Amount']]
            for entry in report_data:
                csv_data.append([date_today, entry['payment_method'], entry['total_sales_amount']])

            # Create CSV response
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="sales_report.csv"'

            # Write CSV data to the response
            writer = csv.writer(response)
            writer.writerows(csv_data)
            return response
        

    context = {
        "sales_today": sales_today,
        "page_obj": page_obj
    }
    return render(request, "reports/sales_today.html", context)
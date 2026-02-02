import os
import win32com.client as w32client


def open_excel(fp):
    # win32com Excel interface can only open files using their absolute paths
    wb_file_path = os.path.abspath(fp)

    # Open workbook
    xlapp = w32client.DispatchEx("Excel.Application")
    xlapp.Interactive = False
    xlapp.Visible = False
    xlapp.DisplayAlerts = False

    wb = xlapp.Workbooks.Open(wb_file_path)

    return xlapp, wb


def close_excel(xlapp, wb):
    wb.Close(SaveChanges=False)
    xlapp.Quit()


def reset_workbook(xlapp, wb, fp):
    """Close and reopen workbook to reset to original state"""
    wb.Close(SaveChanges=False)
    wb = xlapp.Workbooks.Open(fp)

    return wb


# TODO: Use objects to auto-handle state
# class ExcelConn:
#     """Excel file connection"""

#     xlapp
#     wb
#     fp

#     def __init__(self, fp):
#         # win32com Excel interface can only open files using their absolute paths
#         wb_file_path = os.path.abspath(fp)

#         # Open workbook
#         xlapp = w32client.DispatchEx("Excel.Application")
#         xlapp.Interactive = False
#         xlapp.Visible = False
#         xlapp.DisplayAlerts = False

#         wb = xlapp.Workbooks.Open(wb_file_path)
#         self.xlapp = xlapp
#         self.wb = wb
#         self.fp = fp

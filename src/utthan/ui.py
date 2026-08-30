from __future__ import annotations

import calendar
import os
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .database import Database, from_paise
from .reports import (
    MONTHS,
    export_period_csv,
    generate_due_list,
    generate_member_bill,
    generate_receipt,
    open_file,
)


BG = "#F4F7FA"
NAV = "#102A43"
NAV_HOVER = "#243B53"
PRIMARY = "#20639B"
ACCENT = "#2E8B7B"
DANGER = "#C0392B"
TEXT = "#243B53"
MUTED = "#627D98"
BORDER = "#D9E2EC"
WHITE = "#FFFFFF"
PAGE_FRAME = "Page.TFrame"
CARD_FRAME = "Card.TFrame"
CARD_LABEL = "Card.TLabel"
CARD_VALUE = "CardValue.TLabel"
CARD_CAPTION = "CardCaption.TLabel"
PRIMARY_BUTTON = "Primary.TButton"
ACCENT_BUTTON = "Accent.TButton"
SECONDARY_BUTTON = "Secondary.TButton"
FONT_REGULAR = "Segoe UI"
FONT_SEMIBOLD = "Segoe UI Semibold"
ISSUE_LOAN = "Issue Loan"


def money(value: int | None) -> str:
    return f"₹{from_paise(value):,.2f}"


def parse_amount(value: str, label: str = "Amount") -> float:
    try:
        result = float(value.replace(",", "").strip() or "0")
    except ValueError as exc:
        raise ValueError(f"{label} must be a number") from exc
    if result < 0:
        raise ValueError(f"{label} cannot be negative")
    return result


class ScrollFrame(ttk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.body = ttk.Frame(canvas, style=PAGE_FRAME)
        self.body.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


class SocietyApp(tk.Tk):
    def __init__(self, db: Database | None = None) -> None:
        super().__init__()
        self.db = db or Database()
        self.title("Utthan Society Manager")
        self.geometry("1320x820")
        self.minsize(1080, 680)
        self.configure(bg=BG)
        self._configure_styles()
        self._build_shell()
        self.show_dashboard()

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(PAGE_FRAME, background=BG)
        style.configure(CARD_FRAME, background=WHITE, relief="flat")
        style.configure("TLabel", background=BG, foreground=TEXT, font=(FONT_REGULAR, 10))
        style.configure(CARD_LABEL, background=WHITE, foreground=TEXT, font=(FONT_REGULAR, 10))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=(FONT_SEMIBOLD, 22))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=(FONT_REGULAR, 10))
        style.configure(CARD_VALUE, background=WHITE, foreground=TEXT, font=(FONT_SEMIBOLD, 20))
        style.configure(CARD_CAPTION, background=WHITE, foreground=MUTED, font=(FONT_REGULAR, 9))
        style.configure("Section.TLabel", background=BG, foreground=TEXT, font=(FONT_SEMIBOLD, 13))
        style.configure("TButton", font=(FONT_SEMIBOLD, 9), padding=(12, 8), borderwidth=0)
        style.configure(PRIMARY_BUTTON, background=PRIMARY, foreground=WHITE)
        style.map(PRIMARY_BUTTON, background=[("active", "#174F7A")])
        style.configure(ACCENT_BUTTON, background=ACCENT, foreground=WHITE)
        style.map(ACCENT_BUTTON, background=[("active", "#247265")])
        style.configure("Danger.TButton", background=DANGER, foreground=WHITE)
        style.configure(SECONDARY_BUTTON, background="#E8F1F8", foreground=PRIMARY)
        style.map(SECONDARY_BUTTON, background=[("active", "#D6E6F2")])
        style.configure("Treeview", font=(FONT_REGULAR, 9), rowheight=30, background=WHITE,
                        fieldbackground=WHITE, foreground=TEXT, bordercolor=BORDER)
        style.configure("Treeview.Heading", font=(FONT_SEMIBOLD, 9), background="#E8F1F8",
                        foreground=TEXT, relief="flat", padding=(6, 8))
        style.map("Treeview", background=[("selected", PRIMARY)], foreground=[("selected", WHITE)])
        style.configure("TEntry", padding=7, fieldbackground=WHITE)
        style.configure("TCombobox", padding=7, fieldbackground=WHITE)
        style.configure("TLabelframe", background=BG, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=BG, foreground=TEXT,
                font=(FONT_SEMIBOLD, 10))

    def _build_shell(self) -> None:
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True)
        sidebar = tk.Frame(shell, bg=NAV, width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="UTTHAN", bg=NAV, fg=WHITE,
                 font=(FONT_SEMIBOLD, 20)).pack(anchor="w", padx=22, pady=(24, 0))
        tk.Label(sidebar, text="Society Manager", bg=NAV, fg="#9FB3C8",
                 font=(FONT_REGULAR, 9)).pack(anchor="w", padx=23, pady=(0, 24))
        items = [
            ("⌂  Dashboard", self.show_dashboard),
            ("▦  Monthly Dues", self.show_dues),
            ("♙  Members", self.show_members),
            ("₹  Loans", self.show_loans),
            ("↕  Cashbook", self.show_cashbook),
            ("▤  Reports & Backup", self.show_reports),
            ("⚙  Settings", self.show_settings),
        ]
        for label, command in items:
            button = tk.Button(
                sidebar, text=label, command=command, anchor="w", relief="flat",
                bg=NAV, fg="#D9E2EC", activebackground=NAV_HOVER, activeforeground=WHITE,
                font=(FONT_REGULAR, 10), padx=22, pady=12, cursor="hand2", borderwidth=0,
            )
            button.pack(fill="x")
        tk.Label(sidebar, text="Offline • Local data", bg=NAV, fg="#829AB1",
                 font=(FONT_REGULAR, 8)).pack(side="bottom", anchor="w", padx=22, pady=18)
        right = tk.Frame(shell, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self.content = ttk.Frame(right, style=PAGE_FRAME, padding=24)
        self.content.pack(fill="both", expand=True)
        status = tk.Frame(right, bg=WHITE, height=28, highlightbackground=BORDER, highlightthickness=1)
        status.pack(fill="x", side="bottom")
        tk.Label(status, text=f"Data: {self.db.path}", bg=WHITE, fg=MUTED,
                 font=(FONT_REGULAR, 8)).pack(side="left", padx=12, pady=5)

    def clear(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def heading(self, title: str, subtitle: str) -> ttk.Frame:
        area = ttk.Frame(self.content, style=PAGE_FRAME)
        area.pack(fill="x", pady=(0, 18))
        ttk.Label(area, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(area, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))
        return area

    def card(self, parent: tk.Widget, caption: str, value: str, color: str = PRIMARY) -> ttk.Frame:
        frame = ttk.Frame(parent, style=CARD_FRAME, padding=16)
        stripe = tk.Frame(frame, bg=color, width=5)
        stripe.pack(side="left", fill="y", padx=(0, 12))
        text = ttk.Frame(frame, style=CARD_FRAME)
        text.pack(side="left", fill="both", expand=True)
        ttk.Label(text, text=value, style=CARD_VALUE).pack(anchor="w")
        ttk.Label(text, text=caption, style=CARD_CAPTION).pack(anchor="w")
        return frame

    def tree(self, parent: tk.Widget, columns: list[tuple[str, str, int, str]]) -> ttk.Treeview:
        holder = ttk.Frame(parent, style=CARD_FRAME)
        holder.pack(fill="both", expand=True)
        names = [column[0] for column in columns]
        tree = ttk.Treeview(holder, columns=names, show="headings")
        vertical = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(holder, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        for name, label, width, anchor in columns:
            tree.heading(name, text=label)
            tree.column(name, width=width, minwidth=50, anchor=anchor, stretch=width > 150)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        tree.tag_configure("overdue", background="#FFF0EF", foreground="#8A2C23")
        tree.tag_configure("paid", background="#EAF7F3", foreground="#236B5E")
        return tree

    def show_dashboard(self) -> None:
        self.clear()
        stats = self.db.dashboard()
        period = (
            f"{MONTHS[stats['latest_month'] - 1]} {stats['latest_year']}"
            if stats["latest_month"] else "No period"
        )
        self.heading("Dashboard", f"Financial overview • Latest period: {period}")
        cards = ttk.Frame(self.content, style=PAGE_FRAME)
        cards.pack(fill="x")
        for index in range(4):
            cards.columnconfigure(index, weight=1)
        values = [
            ("Active members", str(stats["active_members"]), PRIMARY),
            ("Member savings", money(stats["contributions"]), ACCENT),
            ("Loans in circulation", money(stats["loan_outstanding"]), "#F39C12"),
            ("Available funds", money(stats["available_funds"]), "#7D5BA6"),
        ]
        for index, item in enumerate(values):
            self.card(cards, *item).grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 0 if index == 3 else 6))
        second = ttk.Frame(self.content, style=PAGE_FRAME)
        second.pack(fill="x", pady=12)
        for index in range(3):
            second.columnconfigure(index, weight=1)
        more = [
            ("Interest earned", money(stats["interest_earned"]), PRIMARY),
            ("Total expenses", money(stats["expenses"]), DANGER),
            (f"Collected for {period}", f"{money(stats['period_paid'])} / {money(stats['period_due'])}", ACCENT),
        ]
        for index, item in enumerate(more):
            self.card(second, *item).grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 0 if index == 2 else 6))
        quick = ttk.Frame(self.content, style=PAGE_FRAME)
        quick.pack(fill="x", pady=(5, 16))
        ttk.Button(quick, text="Open Monthly Dues", style=PRIMARY_BUTTON, command=self.show_dues).pack(side="left")
        ttk.Button(quick, text="Add Member", style=SECONDARY_BUTTON, command=self.add_member_dialog).pack(side="left", padx=8)
        ttk.Button(quick, text=ISSUE_LOAN, style=SECONDARY_BUTTON, command=self.issue_loan_dialog).pack(side="left")
        ttk.Label(self.content, text="Recent cashbook entries", style="Section.TLabel").pack(anchor="w", pady=(4, 8))
        tree = self.tree(self.content, [
            ("date", "Date", 100, "center"), ("type", "Type", 150, "w"),
            ("member", "Member", 220, "w"), ("method", "Method", 100, "center"),
            ("amount", "Amount", 130, "e"), ("reference", "Reference", 180, "w"),
        ])
        for row in self.db.transactions(limit=12):
            tree.insert("", "end", values=(row["transaction_date"], row["transaction_type"],
                        row["name"] or "Society", row["payment_method"], money(row["amount_paise"]),
                        row["reference"]))

    def show_members(self) -> None:
        self.clear()
        header = self.heading("Members", "Member register, savings balance and active loans")
        ttk.Button(header, text="+ Add Member", style=PRIMARY_BUTTON, command=self.add_member_dialog).pack(side="right", anchor="e", pady=(0, 5))
        toolbar = ttk.Frame(self.content, style=PAGE_FRAME)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(toolbar, text="Search:").pack(side="left")
        query = tk.StringVar()
        entry = ttk.Entry(toolbar, textvariable=query, width=30)
        entry.pack(side="left", padx=8)
        inactive = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Include inactive", variable=inactive).pack(side="left", padx=10)
        ttk.Button(toolbar, text="Change status", style=SECONDARY_BUTTON,
                   command=lambda: self.change_member_status(tree)).pack(side="right")
        columns = [
            ("no", "No.", 60, "center"), ("name", "Member Name", 240, "w"),
            ("phone", "Phone", 130, "w"), ("join", "Join Date", 110, "center"),
            ("savings", "Savings", 130, "e"), ("loan", "Loan Outstanding", 150, "e"),
            ("status", "Status", 90, "center"),
        ]
        tree = self.tree(self.content, columns)

        def refresh(*_: object) -> None:
            for item in tree.get_children():
                tree.delete(item)
            needle = query.get().strip().lower()
            for row in self.db.list_members(inactive.get()):
                if needle and needle not in row["name"].lower() and needle not in row["phone"].lower():
                    continue
                tree.insert("", "end", iid=str(row["id"]), values=(row["member_no"], row["name"],
                            row["phone"], row["join_date"], money(row["contribution_balance_paise"]),
                            money(row["loan_outstanding_paise"]), row["status"]))
        query.trace_add("write", refresh)
        inactive.trace_add("write", refresh)
        refresh()

    def add_member_dialog(self) -> None:
        dialog = self.form_dialog("Add Member", 520, 540)
        body = dialog.body
        fields: dict[str, tk.StringVar] = {}
        labels = [
            ("name", "Full name *", ""), ("phone", "Phone", ""),
            ("address", "Address", ""), ("nominee", "Nominee", ""),
            ("join_date", "Join date (YYYY-MM-DD)", date.today().isoformat()),
            ("opening", "Opening savings", "0"), ("notes", "Notes", ""),
        ]
        for row_index, (key, label, default) in enumerate(labels):
            ttk.Label(body, text=label, style=CARD_LABEL).grid(row=row_index, column=0, sticky="w", pady=6)
            fields[key] = tk.StringVar(value=default)
            ttk.Entry(body, textvariable=fields[key], width=38).grid(row=row_index, column=1, sticky="ew", pady=6, padx=(12, 0))
        body.columnconfigure(1, weight=1)

        def save() -> None:
            try:
                self.db.add_member(
                    fields["name"].get(), fields["phone"].get(), fields["address"].get(),
                    fields["nominee"].get(), fields["join_date"].get(),
                    parse_amount(fields["opening"].get(), "Opening savings"), fields["notes"].get(),
                )
                dialog.destroy()
                self.show_members()
            except Exception as exc:
                messagebox.showerror("Cannot add member", str(exc), parent=dialog)
        ttk.Button(dialog.buttons, text="Save Member", style=PRIMARY_BUTTON, command=save).pack(side="right")
        ttk.Button(dialog.buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=8)

    def change_member_status(self, tree: ttk.Treeview) -> None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("Select member", "Select a member first.", parent=self)
            return
        member = self.db.member(int(selection[0]))
        if not member:
            return
        new_status = "Inactive" if member["status"] == "Active" else "Active"
        if messagebox.askyesno("Change status", f"Mark {member['name']} as {new_status}?", parent=self):
            self.db.update_member_status(member["id"], new_status)
            self.show_members()

    def show_loans(self) -> None:
        self.clear()
        header = self.heading("Loans", "Track fresh loans, top-ups, EMI and reducing balance")
        ttk.Button(header, text=f"+ {ISSUE_LOAN}", style=PRIMARY_BUTTON, command=self.issue_loan_dialog).pack(side="right", anchor="e")
        tree = self.tree(self.content, [
            ("member", "Member", 230, "w"), ("type", "Type", 90, "center"),
            ("date", "Issue Date", 110, "center"), ("original", "Original Amount", 140, "e"),
            ("balance", "Outstanding", 140, "e"), ("emi", "Monthly EMI", 120, "e"),
            ("rate", "Interest / month", 130, "center"), ("status", "Status", 90, "center"),
            ("notes", "Notes", 240, "w"),
        ])
        for row in self.db.list_loans():
            tree.insert("", "end", iid=str(row["id"]), values=(f"{row['member_no']} - {row['name']}",
                        row["loan_type"], row["issue_date"], money(row["original_amount_paise"]),
                        money(row["outstanding_paise"]), money(row["monthly_emi_paise"]),
                        f"{row['monthly_interest_bp'] / 100:.2f}%", row["status"], row["notes"]))

    def issue_loan_dialog(self) -> None:
        members = self.db.list_members()
        if not members:
            messagebox.showerror("No members", "Add a member before issuing a loan.", parent=self)
            return
        dialog = self.form_dialog(ISSUE_LOAN, 560, 520)
        body = dialog.body
        member_map = {f"{row['member_no']} - {row['name']}": row["id"] for row in members}
        member = tk.StringVar(value=next(iter(member_map)))
        values = {
            "amount": tk.StringVar(value="0"), "date": tk.StringVar(value=date.today().isoformat()),
            "type": tk.StringVar(value="Fresh"),
            "emi": tk.StringVar(value=f"{from_paise(int(self.db.setting('default_emi', '100000'))):.0f}"),
            "rate": tk.StringVar(value=f"{int(self.db.setting('monthly_interest_bp', '150')) / 100:.2f}"),
            "notes": tk.StringVar(),
        }
        labels = ["Member *", "Amount *", "Issue date (YYYY-MM-DD)", "Loan type", "Monthly EMI", "Monthly interest %", "Notes"]
        widgets: list[tk.Widget] = [
            ttk.Combobox(body, textvariable=member, values=list(member_map), state="readonly", width=36),
            ttk.Entry(body, textvariable=values["amount"]), ttk.Entry(body, textvariable=values["date"]),
            ttk.Combobox(body, textvariable=values["type"], values=["Fresh", "Top-up", "Emergency"], state="readonly"),
            ttk.Entry(body, textvariable=values["emi"]), ttk.Entry(body, textvariable=values["rate"]),
            ttk.Entry(body, textvariable=values["notes"]),
        ]
        for index, (label, widget) in enumerate(zip(labels, widgets)):
            ttk.Label(body, text=label, style=CARD_LABEL).grid(row=index, column=0, sticky="w", pady=7)
            widget.grid(row=index, column=1, sticky="ew", pady=7, padx=(12, 0))
        body.columnconfigure(1, weight=1)

        def save() -> None:
            try:
                self.db.issue_loan(member_map[member.get()], parse_amount(values["amount"].get()),
                                   values["date"].get(), values["type"].get(),
                                   parse_amount(values["emi"].get(), "EMI"),
                                   parse_amount(values["rate"].get(), "Interest rate"), values["notes"].get())
                dialog.destroy()
                self.show_loans()
            except Exception as exc:
                messagebox.showerror("Cannot issue loan", str(exc), parent=dialog)
        ttk.Button(dialog.buttons, text=ISSUE_LOAN, style=PRIMARY_BUTTON, command=save).pack(side="right")
        ttk.Button(dialog.buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=8)

    def show_dues(self) -> None:
        self.clear()
        self.heading("Monthly Dues", "Generate bills, record collections and carry unpaid balances forward")
        periods = self.db.list_periods()
        toolbar = ttk.Frame(self.content, style=PAGE_FRAME)
        toolbar.pack(fill="x", pady=(0, 10))
        choices = {f"{MONTHS[row['month'] - 1]} {row['year']} ({row['status']})": row["id"] for row in periods}
        selected = tk.StringVar(value=next(iter(choices), ""))
        ttk.Label(toolbar, text="Period:").pack(side="left")
        combo = ttk.Combobox(toolbar, textvariable=selected, values=list(choices), state="readonly", width=28)
        combo.pack(side="left", padx=8)
        ttk.Button(toolbar, text="Generate Next Month", style=PRIMARY_BUTTON, command=self.generate_next_period).pack(side="left", padx=(4, 12))
        ttk.Button(toolbar, text="Due List PDF", style=SECONDARY_BUTTON,
                   command=lambda: self.make_due_report(choices.get(selected.get()))).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Export CSV", style=SECONDARY_BUTTON,
                   command=lambda: self.make_csv(choices.get(selected.get()))).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Close Period", style="Danger.TButton",
                   command=lambda: self.close_selected_period(choices.get(selected.get()))).pack(side="right")
        actions = ttk.Frame(self.content, style=PAGE_FRAME)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="Record Payment", style=ACCENT_BUTTON,
                   command=lambda: self.payment_dialog(tree)).pack(side="left")
        ttk.Button(actions, text="Generate Member Bill", style=SECONDARY_BUTTON,
                   command=lambda: self.member_bill(tree)).pack(side="left", padx=8)
        search_var = tk.StringVar()
        ttk.Label(actions, text="Search:").pack(side="left", padx=(20, 4))
        ttk.Entry(actions, textvariable=search_var, width=24).pack(side="left")
        tree = self.tree(self.content, [
            ("no", "No.", 55, "center"), ("member", "Member", 210, "w"),
            ("saving", "Contribution", 110, "e"), ("emi", "EMI", 100, "e"),
            ("interest", "Interest", 100, "e"), ("old", "Old Due", 100, "e"),
            ("late", "Late Fee", 90, "e"), ("total", "Total Due", 120, "e"),
            ("paid", "Paid", 110, "e"), ("balance", "Balance", 120, "e"),
            ("status", "Status", 90, "center"),
        ])

        def refresh(*_: object) -> None:
            self._refresh_dues_tree(tree, choices.get(selected.get()), search_var.get())
        selected.trace_add("write", refresh)
        search_var.trace_add("write", refresh)
        refresh()

    def _refresh_dues_tree(self, tree: ttk.Treeview, period_id: int | None, search: str) -> None:
        for item in tree.get_children():
            tree.delete(item)
        if not period_id:
            return
        needle = search.strip().lower()
        for row in self.db.period_dues(period_id):
            if needle and needle not in row["name"].lower():
                continue
            balance = max(0, row["total_due_paise"] - row["total_paid_paise"])
            tag = ""
            if row["status"] == "Paid":
                tag = "paid"
            elif row["arrears_due_paise"]:
                tag = "overdue"
            tree.insert("", "end", iid=str(row["id"]), tags=(tag,), values=(
                row["member_no"], row["name"], money(row["contribution_due_paise"]),
                money(row["emi_due_paise"]), money(row["interest_due_paise"]),
                money(row["arrears_due_paise"]), money(row["late_fee_paise"]),
                money(row["total_due_paise"]), money(row["total_paid_paise"]),
                money(balance), row["status"],
            ))

    def generate_next_period(self) -> None:
        periods = self.db.list_periods()
        if periods:
            year, month = periods[0]["year"], periods[0]["month"]
            if month == 12:
                year, month = year + 1, 1
            else:
                month += 1
        else:
            year, month = date.today().year, date.today().month
        if messagebox.askyesno("Generate dues", f"Generate dues for {MONTHS[month - 1]} {year}?", parent=self):
            self.db.generate_period(year, month)
            self.show_dues()

    def payment_dialog(self, tree: ttk.Treeview) -> None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("Select due", "Select a member due first.", parent=self)
            return
        due = self.db.due(int(selection[0]))
        if not due:
            return
        outstanding = {
            "contribution": due["contribution_due_paise"] - due["contribution_paid_paise"],
            "principal": due["emi_due_paise"] - due["principal_paid_paise"],
            "interest": due["interest_due_paise"] - due["interest_paid_paise"],
            "arrears": due["arrears_due_paise"] - due["arrears_paid_paise"],
            "late_fee": due["late_fee_paise"] - due["late_fee_paid_paise"],
        }
        dialog = self.form_dialog(f"Record Payment - {due['name']}", 590, 610)
        body = dialog.body
        ttk.Label(body, text=f"{MONTHS[due['month'] - 1]} {due['year']} • Balance {money(sum(outstanding.values()))}",
                  style=CARD_LABEL, font=(FONT_SEMIBOLD, 11)).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        values = {key: tk.StringVar(value=f"{from_paise(value):.2f}") for key, value in outstanding.items()}
        values.update({"date": tk.StringVar(value=date.today().isoformat()), "method": tk.StringVar(value="Cash"),
                       "reference": tk.StringVar(), "notes": tk.StringVar()})
        labels = [
            ("contribution", "Contribution"), ("principal", "Loan principal"),
            ("interest", "Interest"), ("arrears", "Previous due"), ("late_fee", "Late fee"),
            ("date", "Payment date (YYYY-MM-DD)"), ("method", "Payment method"),
            ("reference", "Reference / UTR"), ("notes", "Notes"),
        ]
        for index, (key, label) in enumerate(labels, 1):
            ttk.Label(body, text=label, style=CARD_LABEL).grid(row=index, column=0, sticky="w", pady=5)
            if key == "method":
                widget = ttk.Combobox(body, textvariable=values[key], values=["Cash", "Bank Transfer", "UPI", "Cheque"], state="readonly")
            else:
                widget = ttk.Entry(body, textvariable=values[key])
            widget.grid(row=index, column=1, sticky="ew", padx=(12, 0), pady=5)
        body.columnconfigure(1, weight=1)

        def save() -> None:
            try:
                transaction_id = self.db.record_payment(
                    due["id"], *(parse_amount(values[key].get(), label) for key, label in labels[:5]),
                    values["date"].get(), values["method"].get(), values["reference"].get(), values["notes"].get(),
                )
                receipt = generate_receipt(self.db, transaction_id)
                dialog.destroy()
                self.show_dues()
                if messagebox.askyesno("Payment saved", f"Receipt created:\n{receipt}\n\nOpen it now?", parent=self):
                    open_file(receipt)
            except Exception as exc:
                messagebox.showerror("Cannot record payment", str(exc), parent=dialog)
        ttk.Button(dialog.buttons, text="Save & Create Receipt", style=ACCENT_BUTTON, command=save).pack(side="right")
        ttk.Button(dialog.buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=8)

    def member_bill(self, tree: ttk.Treeview) -> None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("Select due", "Select a member due first.", parent=self)
            return
        try:
            path = generate_member_bill(self.db, int(selection[0]))
            open_file(path)
        except Exception as exc:
            messagebox.showerror("Cannot create bill", str(exc), parent=self)

    def make_due_report(self, period_id: int | None) -> None:
        if not period_id:
            return
        try:
            path = generate_due_list(self.db, period_id)
            open_file(path)
        except Exception as exc:
            messagebox.showerror("Cannot create report", str(exc), parent=self)

    def make_csv(self, period_id: int | None) -> None:
        if not period_id:
            return
        try:
            path = export_period_csv(self.db, period_id)
            messagebox.showinfo("Export complete", f"Saved to:\n{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("Cannot export", str(exc), parent=self)

    def close_selected_period(self, period_id: int | None) -> None:
        if not period_id:
            return
        if messagebox.askyesno("Close period", "Close this period? Closed periods cannot accept more payments.", icon="warning", parent=self):
            self.db.close_period(period_id)
            self.show_dues()

    def show_cashbook(self) -> None:
        self.clear()
        header = self.heading("Cashbook", "Member receipts, loan disbursements and society expenses")
        ttk.Button(header, text="+ Add Expense", style=PRIMARY_BUTTON, command=self.expense_dialog).pack(side="right", anchor="e")
        notebook = ttk.Notebook(self.content)
        notebook.pack(fill="both", expand=True)
        transactions_page = ttk.Frame(notebook, style=CARD_FRAME, padding=8)
        expenses_page = ttk.Frame(notebook, style=CARD_FRAME, padding=8)
        notebook.add(transactions_page, text="Transactions")
        notebook.add(expenses_page, text="Expenses")
        tree = self.tree(transactions_page, [
            ("date", "Date", 100, "center"), ("type", "Type", 160, "w"),
            ("member", "Member", 220, "w"), ("method", "Method", 110, "center"),
            ("amount", "Amount", 130, "e"), ("ref", "Reference", 180, "w"),
            ("notes", "Notes", 260, "w"),
        ])
        for row in self.db.transactions():
            tree.insert("", "end", values=(row["transaction_date"], row["transaction_type"], row["name"] or "Society",
                        row["payment_method"], money(row["amount_paise"]), row["reference"], row["notes"]))
        expenses = self.tree(expenses_page, [
            ("date", "Date", 120, "center"), ("category", "Category", 220, "w"),
            ("amount", "Amount", 150, "e"), ("notes", "Notes", 500, "w"),
        ])
        for row in self.db.list_expenses():
            expenses.insert("", "end", values=(row["expense_date"], row["category"], money(row["amount_paise"]), row["notes"]))

    def expense_dialog(self) -> None:
        dialog = self.form_dialog("Add Expense", 500, 390)
        values = {"date": tk.StringVar(value=date.today().isoformat()), "category": tk.StringVar(value="Maintenance"),
                  "amount": tk.StringVar(value="0"), "notes": tk.StringVar()}
        labels = [("date", "Date (YYYY-MM-DD)"), ("category", "Category"), ("amount", "Amount"), ("notes", "Notes")]
        for index, (key, label) in enumerate(labels):
            ttk.Label(dialog.body, text=label, style=CARD_LABEL).grid(row=index, column=0, sticky="w", pady=8)
            ttk.Entry(dialog.body, textvariable=values[key]).grid(row=index, column=1, sticky="ew", padx=(12, 0), pady=8)
        dialog.body.columnconfigure(1, weight=1)

        def save() -> None:
            try:
                self.db.add_expense(values["date"].get(), values["category"].get(),
                                    parse_amount(values["amount"].get()), values["notes"].get())
                dialog.destroy()
                self.show_cashbook()
            except Exception as exc:
                messagebox.showerror("Cannot add expense", str(exc), parent=dialog)
        ttk.Button(dialog.buttons, text="Save Expense", style=PRIMARY_BUTTON, command=save).pack(side="right")
        ttk.Button(dialog.buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=8)

    def show_reports(self) -> None:
        self.clear()
        self.heading("Reports & Backup", "Create printable records and protect the local database")
        area = ttk.Frame(self.content, style=PAGE_FRAME)
        area.pack(fill="both", expand=True)
        area.columnconfigure(0, weight=1)
        area.columnconfigure(1, weight=1)
        report_card = ttk.Frame(area, style=CARD_FRAME, padding=20)
        report_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        backup_card = ttk.Frame(area, style=CARD_FRAME, padding=20)
        backup_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ttk.Label(report_card, text="Monthly reports", style=CARD_VALUE).pack(anchor="w")
        ttk.Label(report_card, text="Choose a period and create a PDF due list or CSV export.", style=CARD_CAPTION).pack(anchor="w", pady=(4, 16))
        periods = self.db.list_periods()
        choices = {f"{MONTHS[row['month'] - 1]} {row['year']}": row["id"] for row in periods}
        selected = tk.StringVar(value=next(iter(choices), ""))
        ttk.Combobox(report_card, textvariable=selected, values=list(choices), state="readonly", width=30).pack(anchor="w")
        ttk.Button(report_card, text="Create Due List PDF", style=PRIMARY_BUTTON,
                   command=lambda: self.make_due_report(choices.get(selected.get()))).pack(anchor="w", pady=(14, 8))
        ttk.Button(report_card, text="Export CSV", style=SECONDARY_BUTTON,
                   command=lambda: self.make_csv(choices.get(selected.get()))).pack(anchor="w")
        ttk.Button(report_card, text="Open Reports Folder", style=SECONDARY_BUTTON,
                   command=lambda: os.startfile(self.db.reports_dir)).pack(anchor="w", pady=(24, 0))  # type: ignore[attr-defined]
        ttk.Label(backup_card, text="Local database backup", style=CARD_VALUE).pack(anchor="w")
        ttk.Label(backup_card, text="Create regular backups and keep a copy on another drive.", style=CARD_CAPTION).pack(anchor="w", pady=(4, 16))
        ttk.Button(backup_card, text="Create Backup Now", style=ACCENT_BUTTON, command=self.create_backup).pack(anchor="w")
        ttk.Button(backup_card, text="Restore From Backup", style=SECONDARY_BUTTON, command=self.restore_backup).pack(anchor="w", pady=8)
        ttk.Button(backup_card, text="Open Backup Folder", style=SECONDARY_BUTTON,
                   command=lambda: os.startfile(self.db.backups_dir)).pack(anchor="w", pady=(16, 0))  # type: ignore[attr-defined]
        ttk.Label(backup_card, text=f"Database location:\n{self.db.path}", style=CARD_CAPTION,
                  wraplength=430, justify="left").pack(anchor="w", pady=(28, 0))

    def create_backup(self) -> None:
        try:
            target = self.db.backup()
            messagebox.showinfo("Backup created", f"Saved to:\n{target}", parent=self)
        except Exception as exc:
            messagebox.showerror("Backup failed", str(exc), parent=self)

    def restore_backup(self) -> None:
        source = filedialog.askopenfilename(parent=self, title="Select database backup", filetypes=[("Database backup", "*.db"), ("All files", "*.*")])
        if not source:
            return
        if not messagebox.askyesno("Restore backup", "Replace current data with this backup? A safety copy will be created first.", icon="warning", parent=self):
            return
        try:
            self.db.restore(Path(source))
            messagebox.showinfo("Restore complete", "The backup was restored successfully.", parent=self)
            self.show_dashboard()
        except Exception as exc:
            messagebox.showerror("Restore failed", str(exc), parent=self)

    def show_settings(self) -> None:
        self.clear()
        self.heading("Settings", "Society identity and default monthly rules")
        card = ttk.Frame(self.content, style=CARD_FRAME, padding=22)
        card.pack(fill="x")
        values = {
            "society_name": tk.StringVar(value=self.db.setting("society_name")),
            "group_name": tk.StringVar(value=self.db.setting("group_name")),
            "monthly_contribution": tk.StringVar(value=f"{from_paise(int(self.db.setting('monthly_contribution', '50000'))):.2f}"),
            "default_emi": tk.StringVar(value=f"{from_paise(int(self.db.setting('default_emi', '100000'))):.2f}"),
            "monthly_interest_bp": tk.StringVar(value=f"{int(self.db.setting('monthly_interest_bp', '150')) / 100:.2f}"),
        }
        labels = [
            ("society_name", "Society name"), ("group_name", "Group name"),
            ("monthly_contribution", "Default monthly contribution"),
            ("default_emi", "Default loan EMI"), ("monthly_interest_bp", "Default monthly interest %"),
        ]
        for index, (key, label) in enumerate(labels):
            ttk.Label(card, text=label, style=CARD_LABEL).grid(row=index, column=0, sticky="w", pady=8)
            ttk.Entry(card, textvariable=values[key], width=42).grid(row=index, column=1, sticky="ew", padx=(20, 0), pady=8)
        card.columnconfigure(1, weight=1)

        def save() -> None:
            try:
                self.db.save_settings({
                    "society_name": values["society_name"].get().strip(),
                    "group_name": values["group_name"].get().strip(),
                    "monthly_contribution": str(round(parse_amount(values["monthly_contribution"].get()) * 100)),
                    "default_emi": str(round(parse_amount(values["default_emi"].get()) * 100)),
                    "monthly_interest_bp": str(round(parse_amount(values["monthly_interest_bp"].get()) * 100)),
                })
                messagebox.showinfo("Settings saved", "New defaults apply when future periods and loans are created.", parent=self)
            except Exception as exc:
                messagebox.showerror("Cannot save settings", str(exc), parent=self)
        ttk.Button(card, text="Save Settings", style=PRIMARY_BUTTON, command=save).grid(row=len(labels), column=1, sticky="e", pady=(18, 0))
        note = ttk.Frame(self.content, style=CARD_FRAME, padding=18)
        note.pack(fill="x", pady=14)
        ttk.Label(note, text="Important", style=CARD_VALUE).pack(anchor="w")
        ttk.Label(note, style=CARD_LABEL, wraplength=850, justify="left",
                  text="Existing monthly dues keep the rate and amounts used when they were generated. Changing defaults does not rewrite historical records. Each loan also keeps its own interest rate and EMI.").pack(anchor="w", pady=(5, 0))

    def form_dialog(self, title: str, width: int, height: int):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry(f"{width}x{height}")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        outer = ttk.Frame(dialog, style=CARD_FRAME, padding=22)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=title, style=CARD_VALUE).pack(anchor="w", pady=(0, 14))
        dialog.body = ttk.Frame(outer, style=CARD_FRAME)  # type: ignore[attr-defined]
        dialog.body.pack(fill="both", expand=True)  # type: ignore[attr-defined]
        dialog.buttons = ttk.Frame(outer, style=CARD_FRAME)  # type: ignore[attr-defined]
        dialog.buttons.pack(fill="x", pady=(16, 0))  # type: ignore[attr-defined]
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - width) // 2
        y = self.winfo_y() + (self.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        return dialog


def run() -> None:
    app = SocietyApp()
    app.mainloop()

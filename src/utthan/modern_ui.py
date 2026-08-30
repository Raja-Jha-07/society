from __future__ import annotations

import os
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from .database import Database, from_paise
from .reports import (
    MONTHS,
    export_period_csv,
    generate_due_list,
    generate_member_bill,
    generate_receipt,
    open_file,
)

# Modern light visual system
APP_BG = "#F5F7FB"
SURFACE = "#FFFFFF"
SIDEBAR = "#101828"
SIDEBAR_HOVER = "#1D2939"
PRIMARY = "#635BFF"
PRIMARY_HOVER = "#5148E5"
TEAL = "#12B76A"
TEAL_SOFT = "#ECFDF3"
BLUE = "#2E90FA"
BLUE_SOFT = "#EFF8FF"
AMBER = "#F79009"
AMBER_SOFT = "#FFFAEB"
RED = "#F04438"
RED_SOFT = "#FEF3F2"
PURPLE_SOFT = "#F4F3FF"
TEXT = "#101828"
TEXT_SECONDARY = "#475467"
MUTED = "#98A2B3"
BORDER = "#EAECF0"
FONT = "Segoe UI"
FONT_MEDIUM = "Segoe UI Semibold"
TREE_STYLE = "Modern.Treeview"

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


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


class Modal(ctk.CTkToplevel):
    def __init__(self, parent: "ModernSocietyApp", title: str, width: int, height: int) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        self.transient(parent)
        self.configure(fg_color=APP_BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=76)
        header.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(header, text=title, text_color=TEXT,
                     font=(FONT_MEDIUM, 20)).pack(side="left", padx=24, pady=22)
        ctk.CTkButton(header, text="×", width=34, height=34, corner_radius=17,
                      fg_color="#F2F4F7", hover_color=BORDER, text_color=TEXT_SECONDARY,
                      font=(FONT, 20), command=self.destroy).pack(side="right", padx=20)
        self.body = ctk.CTkScrollableFrame(
            self, fg_color=APP_BG, corner_radius=0,
            scrollbar_button_color="#D0D5DD", scrollbar_button_hover_color=MUTED,
        )
        self.body.grid(row=1, column=0, sticky="nsew", padx=18, pady=12)
        self.body.grid_columnconfigure(1, weight=1)
        self.buttons = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=72)
        self.buttons.grid(row=2, column=0, sticky="ew")
        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - width) // 2
        y = parent.winfo_y() + (parent.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self.after(50, self.grab_set)


class ModernSocietyApp(ctk.CTk):
    def __init__(self, db: Database | None = None) -> None:
        super().__init__()
        self.db = db or Database()
        self.title("Utthan Society Manager")
        self.geometry("1440x900")
        self.minsize(1120, 720)
        self.configure(fg_color=APP_BG)
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.active_page = ""
        self._configure_table_style()
        self._build_shell()
        self.navigate("dashboard", self.show_dashboard)

    def _configure_table_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            TREE_STYLE, background=SURFACE, fieldbackground=SURFACE,
            foreground=TEXT_SECONDARY, rowheight=36, borderwidth=0,
            relief="flat", font=(FONT, 9),
        )
        style.configure(
            "Modern.Treeview.Heading", background="#F9FAFB", foreground=TEXT_SECONDARY,
            borderwidth=0, relief="flat", padding=(9, 11), font=(FONT_MEDIUM, 9),
        )
        style.map(
            TREE_STYLE, background=[("selected", PURPLE_SOFT)],
            foreground=[("selected", TEXT)],
        )
        style.map("Modern.Treeview.Heading", background=[("active", "#F2F4F7")])

    def _build_shell(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        sidebar = ctk.CTkFrame(self, width=246, corner_radius=0, fg_color=SIDEBAR)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(9, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(24, 30))
        mark = ctk.CTkLabel(
            brand, text="U", width=42, height=42, corner_radius=12,
            fg_color=PRIMARY, text_color="white", font=(FONT_MEDIUM, 20),
        )
        mark.pack(side="left")
        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left", padx=11)
        ctk.CTkLabel(brand_text, text="UTTHAN", text_color="white",
                     font=(FONT_MEDIUM, 17)).pack(anchor="w")
        ctk.CTkLabel(brand_text, text="Society Manager", text_color="#98A2B3",
                     font=(FONT, 10)).pack(anchor="w")

        ctk.CTkLabel(sidebar, text="WORKSPACE", text_color="#667085",
                     font=(FONT_MEDIUM, 9)).grid(row=1, column=0, sticky="w", padx=26, pady=(0, 8))
        nav_items = [
            ("dashboard", "Overview", "⌂", self.show_dashboard),
            ("dues", "Monthly dues", "▦", self.show_dues),
            ("members", "Members", "♙", self.show_members),
            ("loans", "Loans", "₹", self.show_loans),
            ("cashbook", "Cashbook", "↕", self.show_cashbook),
            ("reports", "Reports & backup", "▤", self.show_reports),
            ("settings", "Settings", "⚙", self.show_settings),
        ]
        for index, (key, label, icon, command) in enumerate(nav_items, 2):
            button = ctk.CTkButton(
                sidebar, text=f"  {icon}    {label}", anchor="w", width=210, height=44,
                corner_radius=9, fg_color="transparent", hover_color=SIDEBAR_HOVER,
                text_color="#D0D5DD", font=(FONT, 11),
                command=lambda k=key, c=command: self.navigate(k, c),
            )
            button.grid(row=index, column=0, padx=18, pady=3)
            self.nav_buttons[key] = button

        profile = ctk.CTkFrame(sidebar, fg_color="#1D2939", corner_radius=12)
        profile.grid(row=10, column=0, sticky="ew", padx=18, pady=18)
        dot = ctk.CTkLabel(profile, text="●", text_color=TEAL, width=18,
                           font=(FONT, 12))
        dot.pack(side="left", padx=(13, 3), pady=13)
        info = ctk.CTkFrame(profile, fg_color="transparent")
        info.pack(side="left", pady=10)
        ctk.CTkLabel(info, text="Offline mode", text_color="white",
                     font=(FONT_MEDIUM, 10)).pack(anchor="w")
        ctk.CTkLabel(info, text="Data stays on this PC", text_color="#98A2B3",
                     font=(FONT, 8)).pack(anchor="w")

        main = ctk.CTkFrame(self, fg_color=APP_BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        topbar = ctk.CTkFrame(main, fg_color=SURFACE, corner_radius=0, height=68,
                              border_width=1, border_color=BORDER)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)
        ctk.CTkLabel(
            topbar, text=datetime.now().strftime("%A, %d %B %Y"),
            text_color=TEXT_SECONDARY, font=(FONT, 10),
        ).pack(side="left", padx=28)
        ctk.CTkLabel(
            topbar, text="LOCAL DATABASE", corner_radius=12, height=26,
            fg_color=TEAL_SOFT, text_color="#027A48", font=(FONT_MEDIUM, 8),
        ).pack(side="right", padx=28)
        self.content = ctk.CTkFrame(main, fg_color=APP_BG, corner_radius=0)
        self.content.grid(row=1, column=0, sticky="nsew", padx=28, pady=24)

    def navigate(self, key: str, command) -> None:
        self.active_page = key
        for name, button in self.nav_buttons.items():
            active = name == key
            button.configure(
                fg_color=PRIMARY if active else "transparent",
                hover_color=PRIMARY_HOVER if active else SIDEBAR_HOVER,
                text_color="white" if active else "#D0D5DD",
                font=(FONT_MEDIUM if active else FONT, 11),
            )
        command()

    def clear(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def page_header(self, title: str, subtitle: str) -> ctk.CTkFrame:
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        text = ctk.CTkFrame(header, fg_color="transparent")
        text.pack(side="left")
        ctk.CTkLabel(text, text=title, text_color=TEXT,
                     font=(FONT_MEDIUM, 26)).pack(anchor="w")
        ctk.CTkLabel(text, text=subtitle, text_color=TEXT_SECONDARY,
                     font=(FONT, 10)).pack(anchor="w", pady=(3, 0))
        return header

    def button(
        self, parent, text: str, command, variant: str = "primary", width: int = 120,
    ) -> ctk.CTkButton:
        palette = {
            "primary": (PRIMARY, PRIMARY_HOVER, "white"),
            "success": (TEAL, "#039855", "white"),
            "danger": ("transparent", RED_SOFT, RED),
            "secondary": (SURFACE, "#F2F4F7", TEXT_SECONDARY),
        }
        fg, hover, text_color = palette[variant]
        border_width = 1 if variant in {"secondary", "danger"} else 0
        border_color = fg
        if variant == "secondary":
            border_color = BORDER
        elif variant == "danger":
            border_color = "#FECDCA"
        return ctk.CTkButton(
            parent, text=text, command=command, width=width, height=38,
            corner_radius=9, fg_color=fg, hover_color=hover, text_color=text_color,
            border_width=border_width, border_color=border_color,
            font=(FONT_MEDIUM, 9),
        )

    def metric_card(
        self, parent, title: str, value: str, icon: str, icon_fg: str,
        icon_color: str, note: str,
    ) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER,
        )
        card.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=17, pady=(16, 8))
        ctk.CTkLabel(top, text=title, text_color=TEXT_SECONDARY,
                     font=(FONT_MEDIUM, 9)).pack(side="left")
        ctk.CTkLabel(
            top, text=icon, width=34, height=34, corner_radius=10,
            fg_color=icon_fg, text_color=icon_color, font=(FONT_MEDIUM, 14),
        ).pack(side="right")
        ctk.CTkLabel(card, text=value, text_color=TEXT,
                     font=(FONT_MEDIUM, 21)).pack(anchor="w", padx=17)
        ctk.CTkLabel(card, text=note, text_color=MUTED,
                     font=(FONT, 8)).pack(anchor="w", padx=17, pady=(5, 16))
        return card

    def section_card(self, parent, title: str, subtitle: str = "") -> tuple[ctk.CTkFrame, ctk.CTkFrame]:
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14,
                            border_width=1, border_color=BORDER)
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(16, 12))
        labels = ctk.CTkFrame(header, fg_color="transparent")
        labels.pack(side="left")
        ctk.CTkLabel(labels, text=title, text_color=TEXT,
                     font=(FONT_MEDIUM, 13)).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(labels, text=subtitle, text_color=MUTED,
                         font=(FONT, 8)).pack(anchor="w", pady=(2, 0))
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        return card, body

    def tree(
        self, parent, columns: list[tuple[str, str, int, str]], height: int = 10,
    ) -> ttk.Treeview:
        holder = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=12,
                              border_width=1, border_color=BORDER)
        holder.pack(fill="both", expand=True)
        holder.grid_columnconfigure(0, weight=1)
        holder.grid_rowconfigure(0, weight=1)
        names = [column[0] for column in columns]
        tree = ttk.Treeview(holder, columns=names, show="headings", style=TREE_STYLE, height=height)
        ybar = ctk.CTkScrollbar(holder, orientation="vertical", command=tree.yview,
                                button_color="#D0D5DD", button_hover_color=MUTED, width=12)
        xbar = ctk.CTkScrollbar(holder, orientation="horizontal", command=tree.xview,
                                button_color="#D0D5DD", button_hover_color=MUTED, height=12)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        for name, label, width, anchor in columns:
            tree.heading(name, text=label)
            tree.column(name, width=width, minwidth=55, anchor=anchor, stretch=width > 160)
        tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=(8, 0))
        ybar.grid(row=0, column=1, sticky="ns", padx=(4, 8), pady=8)
        xbar.grid(row=1, column=0, sticky="ew", padx=10, pady=(4, 8))
        tree.tag_configure("paid", background=TEAL_SOFT, foreground="#027A48")
        tree.tag_configure("overdue", background=RED_SOFT, foreground="#B42318")
        tree.tag_configure("inactive", foreground=MUTED)
        return tree

    def show_dashboard(self) -> None:
        self.clear()
        stats = self.db.dashboard()
        period = (
            f"{MONTHS[stats['latest_month'] - 1]} {stats['latest_year']}"
            if stats["latest_month"] else "No period"
        )
        header = self.page_header("Good day", "Here is the latest financial position of the society.")
        self.button(header, "+ Record payment", lambda: self.navigate("dues", self.show_dues),
                    "primary", 142).pack(side="right")

        metrics = ctk.CTkFrame(self.content, fg_color="transparent")
        metrics.pack(fill="x")
        for index in range(4):
            metrics.grid_columnconfigure(index, weight=1, uniform="metric")
        cards = [
            ("Active members", str(stats["active_members"]), "M", BLUE_SOFT, BLUE, "Current member register"),
            ("Member savings", money(stats["contributions"]), "S", TEAL_SOFT, TEAL, "Total contributions received"),
            ("Loans in circulation", money(stats["loan_outstanding"]), "₹", AMBER_SOFT, AMBER, "Outstanding member principal"),
            ("Available funds", money(stats["available_funds"]), "A", PURPLE_SOFT, PRIMARY, "Corpus less active loans"),
        ]
        for index, values in enumerate(cards):
            self.metric_card(metrics, *values).grid(
                row=0, column=index, sticky="nsew",
                padx=(0 if index == 0 else 6, 0 if index == 3 else 6),
            )

        middle = ctk.CTkFrame(self.content, fg_color="transparent")
        middle.pack(fill="x", pady=14)
        middle.grid_columnconfigure(0, weight=2)
        middle.grid_columnconfigure(1, weight=1)
        progress_card, progress_body = self.section_card(
            middle, f"Collection progress · {period}", "Live against the generated monthly dues",
        )
        progress_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        total_due = stats["period_due"]
        ratio = min(1, stats["period_paid"] / total_due) if total_due else 0
        row = ctk.CTkFrame(progress_body, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(4, 8))
        ctk.CTkLabel(row, text=money(stats["period_paid"]), text_color=TEXT,
                     font=(FONT_MEDIUM, 22)).pack(side="left")
        ctk.CTkLabel(row, text=f"of {money(total_due)}", text_color=MUTED,
                     font=(FONT, 9)).pack(side="left", padx=7, pady=(7, 0))
        ctk.CTkLabel(row, text=f"{ratio * 100:.0f}%", text_color=PRIMARY,
                     font=(FONT_MEDIUM, 11)).pack(side="right")
        bar = ctk.CTkProgressBar(progress_body, height=10, corner_radius=5,
                                 progress_color=PRIMARY, fg_color="#EAECF0")
        bar.pack(fill="x", padx=8, pady=(0, 16))
        bar.set(ratio)

        quick_card, quick_body = self.section_card(middle, "Quick actions", "Common monthly tasks")
        quick_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self.button(quick_body, "Add member", self.add_member_dialog, "secondary", 118).pack(side="left", padx=(8, 5), pady=8)
        self.button(quick_body, "Issue loan", self.issue_loan_dialog, "secondary", 118).pack(side="left", padx=5, pady=8)

        lower = ctk.CTkFrame(self.content, fg_color="transparent")
        lower.pack(fill="both", expand=True)
        card, body = self.section_card(lower, "Recent activity", "Latest entries from the local cashbook")
        card.pack(fill="both", expand=True)
        table = self.tree(body, [
            ("date", "DATE", 105, "center"), ("type", "TYPE", 165, "w"),
            ("member", "MEMBER", 230, "w"), ("method", "METHOD", 110, "center"),
            ("amount", "AMOUNT", 135, "e"), ("reference", "REFERENCE", 190, "w"),
        ], height=7)
        for item in self.db.transactions(limit=10):
            table.insert("", "end", values=(
                item["transaction_date"], item["transaction_type"], item["name"] or "Society",
                item["payment_method"], money(item["amount_paise"]), item["reference"] or "—",
            ))

    def show_members(self) -> None:
        self.clear()
        header = self.page_header("Members", "Manage the member register, savings and account status.")
        self.button(header, "+ Add member", self.add_member_dialog, "primary", 125).pack(side="right")
        controls = ctk.CTkFrame(self.content, fg_color="transparent")
        controls.pack(fill="x", pady=(0, 12))
        query = tk.StringVar()
        search = ctk.CTkEntry(
            controls, textvariable=query, placeholder_text="Search member or phone…",
            width=300, height=40, corner_radius=9, border_color=BORDER,
            fg_color=SURFACE, text_color=TEXT,
        )
        search.pack(side="left")
        include_inactive = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            controls, text="Include inactive", variable=include_inactive,
            progress_color=PRIMARY, button_color="white", text_color=TEXT_SECONDARY,
            font=(FONT, 9),
        ).pack(side="left", padx=16)
        table = self.tree(self.content, [
            ("no", "NO.", 60, "center"), ("name", "MEMBER NAME", 245, "w"),
            ("phone", "PHONE", 130, "w"), ("join", "JOIN DATE", 110, "center"),
            ("savings", "SAVINGS", 135, "e"), ("loan", "LOAN OUTSTANDING", 160, "e"),
            ("status", "STATUS", 100, "center"),
        ], height=14)
        self.button(controls, "Change status", lambda: self.change_member_status(table),
                    "secondary", 125).pack(side="right")

        def refresh(*_: object) -> None:
            for item in table.get_children():
                table.delete(item)
            needle = query.get().strip().lower()
            for row in self.db.list_members(include_inactive.get()):
                if needle and needle not in row["name"].lower() and needle not in row["phone"].lower():
                    continue
                tag = "inactive" if row["status"] == "Inactive" else ""
                table.insert("", "end", iid=str(row["id"]), tags=(tag,), values=(
                    row["member_no"], row["name"], row["phone"] or "—", row["join_date"],
                    money(row["contribution_balance_paise"]), money(row["loan_outstanding_paise"]),
                    row["status"],
                ))
        query.trace_add("write", refresh)
        include_inactive.trace_add("write", refresh)
        refresh()

    def add_member_dialog(self) -> None:
        dialog = Modal(self, "Add new member", 570, 650)
        fields: dict[str, ctk.CTkEntry] = {}
        items = [
            ("name", "Full name", "Required"), ("phone", "Phone", "Optional"),
            ("address", "Address", "Optional"), ("nominee", "Nominee", "Optional"),
            ("join_date", "Join date", date.today().isoformat()),
            ("opening", "Opening savings", "0"), ("notes", "Notes", "Optional"),
        ]
        for index, (key, label, placeholder) in enumerate(items):
            self.form_label(dialog.body, label, index)
            entry = self.form_entry(dialog.body, index, placeholder)
            if key == "join_date":
                entry.insert(0, date.today().isoformat())
            elif key == "opening":
                entry.insert(0, "0")
            fields[key] = entry

        def save() -> None:
            try:
                self.db.add_member(
                    fields["name"].get(), fields["phone"].get(), fields["address"].get(),
                    fields["nominee"].get(), fields["join_date"].get(),
                    parse_amount(fields["opening"].get(), "Opening savings"), fields["notes"].get(),
                )
                dialog.destroy()
                self.navigate("members", self.show_members)
            except Exception as exc:
                messagebox.showerror("Cannot add member", str(exc), parent=dialog)
        self.modal_buttons(dialog, "Save member", save)

    def change_member_status(self, table: ttk.Treeview) -> None:
        selection = table.selection()
        if not selection:
            messagebox.showinfo("Select member", "Select a member first.", parent=self)
            return
        member = self.db.member(int(selection[0]))
        if not member:
            return
        new_status = "Inactive" if member["status"] == "Active" else "Active"
        if messagebox.askyesno("Change status", f"Mark {member['name']} as {new_status}?", parent=self):
            self.db.update_member_status(member["id"], new_status)
            self.navigate("members", self.show_members)

    def show_loans(self) -> None:
        self.clear()
        header = self.page_header("Loans", "Track disbursements, reducing balances and repayment terms.")
        self.button(header, "+ Issue loan", self.issue_loan_dialog, "primary", 125).pack(side="right")
        summary = ctk.CTkFrame(self.content, fg_color="transparent")
        summary.pack(fill="x", pady=(0, 12))
        loans = self.db.list_loans()
        open_loans = [row for row in loans if row["status"] == "Open"]
        ctk.CTkLabel(summary, text=f"{len(open_loans)} active loans", text_color="#027A48",
                     fg_color=TEAL_SOFT, corner_radius=12, height=28,
                     font=(FONT_MEDIUM, 9)).pack(side="left")
        table = self.tree(self.content, [
            ("member", "MEMBER", 220, "w"), ("type", "TYPE", 90, "center"),
            ("date", "ISSUE DATE", 105, "center"), ("original", "ORIGINAL", 130, "e"),
            ("balance", "OUTSTANDING", 135, "e"), ("emi", "MONTHLY EMI", 120, "e"),
            ("rate", "MONTHLY RATE", 120, "center"), ("status", "STATUS", 90, "center"),
            ("notes", "NOTES", 220, "w"),
        ], height=15)
        for row in loans:
            tag = "paid" if row["status"] == "Closed" else ""
            table.insert("", "end", iid=str(row["id"]), tags=(tag,), values=(
                f"{row['member_no']} · {row['name']}", row["loan_type"], row["issue_date"],
                money(row["original_amount_paise"]), money(row["outstanding_paise"]),
                money(row["monthly_emi_paise"]), f"{row['monthly_interest_bp'] / 100:.2f}%",
                row["status"], row["notes"] or "—",
            ))

    def issue_loan_dialog(self) -> None:
        members = self.db.list_members()
        if not members:
            messagebox.showerror("No members", "Add a member before issuing a loan.", parent=self)
            return
        dialog = Modal(self, "Issue member loan", 600, 620)
        member_map = {f"{row['member_no']} · {row['name']}": row["id"] for row in members}
        labels = ["Member", "Amount", "Issue date", "Loan type", "Monthly EMI", "Monthly interest %", "Notes"]
        for index, label in enumerate(labels):
            self.form_label(dialog.body, label, index)
        member = ctk.CTkComboBox(dialog.body, values=list(member_map), height=38, corner_radius=8,
                                 border_color=BORDER, fg_color=SURFACE, button_color=PRIMARY,
                                 button_hover_color=PRIMARY_HOVER)
        member.grid(row=0, column=1, sticky="ew", padx=(14, 4), pady=6)
        member.set(next(iter(member_map)))
        amount = self.form_entry(dialog.body, 1, "0"); amount.insert(0, "0")
        issue_date = self.form_entry(dialog.body, 2, "YYYY-MM-DD"); issue_date.insert(0, date.today().isoformat())
        loan_type = ctk.CTkComboBox(dialog.body, values=["Fresh", "Top-up", "Emergency"], height=38,
                                    border_color=BORDER, fg_color=SURFACE, button_color=PRIMARY,
                                    button_hover_color=PRIMARY_HOVER)
        loan_type.grid(row=3, column=1, sticky="ew", padx=(14, 4), pady=6); loan_type.set("Fresh")
        emi = self.form_entry(dialog.body, 4, "1000"); emi.insert(0, f"{from_paise(int(self.db.setting('default_emi', '100000'))):.0f}")
        rate = self.form_entry(dialog.body, 5, "1.5"); rate.insert(0, f"{int(self.db.setting('monthly_interest_bp', '150')) / 100:.2f}")
        notes = self.form_entry(dialog.body, 6, "Optional")

        def save() -> None:
            try:
                self.db.issue_loan(
                    member_map[member.get()], parse_amount(amount.get()), issue_date.get(),
                    loan_type.get(), parse_amount(emi.get(), "EMI"),
                    parse_amount(rate.get(), "Interest rate"), notes.get(),
                )
                dialog.destroy()
                self.navigate("loans", self.show_loans)
            except Exception as exc:
                messagebox.showerror("Cannot issue loan", str(exc), parent=dialog)
        self.modal_buttons(dialog, "Issue loan", save)

    def show_dues(self) -> None:
        self.clear()
        self.page_header("Monthly dues", "Generate monthly demand, collect payments and issue receipts.")
        periods = self.db.list_periods()
        choices = {f"{MONTHS[row['month'] - 1]} {row['year']}  ·  {row['status']}": row["id"] for row in periods}
        selected = tk.StringVar(value=next(iter(choices), ""))
        tools = ctk.CTkFrame(self.content, fg_color=SURFACE, corner_radius=12,
                             border_width=1, border_color=BORDER)
        tools.pack(fill="x", pady=(0, 12))
        period_combo = ctk.CTkComboBox(
            tools, variable=selected, values=list(choices), width=225, height=38,
            corner_radius=8, border_color=BORDER, fg_color=SURFACE,
            button_color=PRIMARY, button_hover_color=PRIMARY_HOVER,
        )
        period_combo.pack(side="left", padx=12, pady=11)
        self.button(tools, "Generate next", self.generate_next_period, "primary", 118).pack(side="left", padx=4)
        self.button(tools, "Due-list PDF", lambda: self.make_due_report(choices.get(selected.get())),
                    "secondary", 110).pack(side="left", padx=4)
        self.button(tools, "Export CSV", lambda: self.make_csv(choices.get(selected.get())),
                    "secondary", 100).pack(side="left", padx=4)
        self.button(tools, "Close period", lambda: self.close_selected_period(choices.get(selected.get())),
                    "danger", 108).pack(side="right", padx=12)

        actions = ctk.CTkFrame(self.content, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 10))
        query = tk.StringVar()
        ctk.CTkEntry(actions, textvariable=query, placeholder_text="Search member…", width=260,
                     height=38, corner_radius=9, border_color=BORDER, fg_color=SURFACE).pack(side="left")
        table = self.tree(self.content, [
            ("no", "NO.", 55, "center"), ("member", "MEMBER", 205, "w"),
            ("saving", "CONTRIBUTION", 110, "e"), ("emi", "EMI", 95, "e"),
            ("interest", "INTEREST", 95, "e"), ("old", "OLD DUE", 95, "e"),
            ("late", "LATE FEE", 85, "e"), ("total", "TOTAL DUE", 115, "e"),
            ("paid", "PAID", 105, "e"), ("balance", "BALANCE", 110, "e"),
            ("status", "STATUS", 90, "center"),
        ], height=13)
        self.button(actions, "Record payment", lambda: self.payment_dialog(table),
                    "success", 130).pack(side="right")
        self.button(actions, "Member bill", lambda: self.member_bill(table),
                    "secondary", 110).pack(side="right", padx=8)

        def refresh(*_: object) -> None:
            self._refresh_dues(table, choices.get(selected.get()), query.get())
        selected.trace_add("write", refresh)
        query.trace_add("write", refresh)
        refresh()

    def _refresh_dues(self, table: ttk.Treeview, period_id: int | None, search: str) -> None:
        for item in table.get_children():
            table.delete(item)
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
            table.insert("", "end", iid=str(row["id"]), tags=(tag,), values=(
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
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        else:
            year, month = date.today().year, date.today().month
        if messagebox.askyesno("Generate dues", f"Generate dues for {MONTHS[month - 1]} {year}?", parent=self):
            self.db.generate_period(year, month)
            self.navigate("dues", self.show_dues)

    def payment_dialog(self, table: ttk.Treeview) -> None:
        selection = table.selection()
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
        dialog = Modal(self, f"Payment · {due['name']}", 610, 720)
        banner = ctk.CTkFrame(dialog.body, fg_color=PURPLE_SOFT, corner_radius=10)
        banner.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(0, 12))
        ctk.CTkLabel(banner, text=f"{MONTHS[due['month'] - 1]} {due['year']}", text_color=PRIMARY,
                     font=(FONT_MEDIUM, 10)).pack(side="left", padx=14, pady=12)
        ctk.CTkLabel(banner, text=f"Balance  {money(sum(outstanding.values()))}", text_color=TEXT,
                     font=(FONT_MEDIUM, 12)).pack(side="right", padx=14)
        labels = [
            ("contribution", "Contribution"), ("principal", "Loan principal"),
            ("interest", "Interest"), ("arrears", "Previous due"), ("late_fee", "Late fee"),
        ]
        entries: dict[str, ctk.CTkEntry] = {}
        for index, (key, label) in enumerate(labels, 1):
            self.form_label(dialog.body, label, index)
            entry = self.form_entry(dialog.body, index, "0")
            entry.insert(0, f"{from_paise(outstanding[key]):.2f}")
            entries[key] = entry
        self.form_label(dialog.body, "Payment date", 6)
        payment_date = self.form_entry(dialog.body, 6, "YYYY-MM-DD"); payment_date.insert(0, date.today().isoformat())
        self.form_label(dialog.body, "Payment method", 7)
        method = ctk.CTkComboBox(dialog.body, values=["Cash", "Bank Transfer", "UPI", "Cheque"],
                                 height=38, border_color=BORDER, fg_color=SURFACE,
                                 button_color=PRIMARY, button_hover_color=PRIMARY_HOVER)
        method.grid(row=7, column=1, sticky="ew", padx=(14, 4), pady=6); method.set("Cash")
        self.form_label(dialog.body, "Reference / UTR", 8)
        reference = self.form_entry(dialog.body, 8, "Optional")
        self.form_label(dialog.body, "Notes", 9)
        notes = self.form_entry(dialog.body, 9, "Optional")

        def save() -> None:
            try:
                transaction_id = self.db.record_payment(
                    due["id"], parse_amount(entries["contribution"].get(), "Contribution"),
                    parse_amount(entries["principal"].get(), "Principal"),
                    parse_amount(entries["interest"].get(), "Interest"),
                    parse_amount(entries["arrears"].get(), "Previous due"),
                    parse_amount(entries["late_fee"].get(), "Late fee"),
                    payment_date.get(), method.get(), reference.get(), notes.get(),
                )
                receipt = generate_receipt(self.db, transaction_id)
                dialog.destroy()
                self.navigate("dues", self.show_dues)
                if messagebox.askyesno("Payment saved", "Receipt created successfully.\n\nOpen it now?", parent=self):
                    open_file(receipt)
            except Exception as exc:
                messagebox.showerror("Cannot record payment", str(exc), parent=dialog)
        self.modal_buttons(dialog, "Save & create receipt", save, 170, "success")

    def member_bill(self, table: ttk.Treeview) -> None:
        selection = table.selection()
        if not selection:
            messagebox.showinfo("Select due", "Select a member due first.", parent=self)
            return
        try:
            open_file(generate_member_bill(self.db, int(selection[0])))
        except Exception as exc:
            messagebox.showerror("Cannot create bill", str(exc), parent=self)

    def make_due_report(self, period_id: int | None) -> None:
        if not period_id:
            return
        try:
            open_file(generate_due_list(self.db, period_id))
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
        if messagebox.askyesno(
            "Close period", "Close this period? Closed periods cannot accept more payments.",
            icon="warning", parent=self,
        ):
            self.db.close_period(period_id)
            self.navigate("dues", self.show_dues)

    def show_cashbook(self) -> None:
        self.clear()
        header = self.page_header("Cashbook", "Review money movement, disbursements and society expenses.")
        self.button(header, "+ Add expense", self.expense_dialog, "primary", 125).pack(side="right")
        tabs = ctk.CTkTabview(
            self.content, fg_color=SURFACE, segmented_button_fg_color="#F2F4F7",
            segmented_button_selected_color=PRIMARY, segmented_button_selected_hover_color=PRIMARY_HOVER,
            segmented_button_unselected_color="#F2F4F7", segmented_button_unselected_hover_color=BORDER,
            text_color=TEXT, corner_radius=14, border_width=1, border_color=BORDER,
        )
        tabs.pack(fill="both", expand=True)
        transactions_tab = tabs.add("Transactions")
        expenses_tab = tabs.add("Expenses")
        transactions_tab.configure(fg_color=SURFACE)
        expenses_tab.configure(fg_color=SURFACE)
        table = self.tree(transactions_tab, [
            ("date", "DATE", 105, "center"), ("type", "TYPE", 170, "w"),
            ("member", "MEMBER", 220, "w"), ("method", "METHOD", 110, "center"),
            ("amount", "AMOUNT", 130, "e"), ("ref", "REFERENCE", 170, "w"),
            ("notes", "NOTES", 240, "w"),
        ], height=13)
        for row in self.db.transactions():
            table.insert("", "end", values=(
                row["transaction_date"], row["transaction_type"], row["name"] or "Society",
                row["payment_method"], money(row["amount_paise"]), row["reference"] or "—",
                row["notes"] or "—",
            ))
        expense_table = self.tree(expenses_tab, [
            ("date", "DATE", 120, "center"), ("category", "CATEGORY", 220, "w"),
            ("amount", "AMOUNT", 150, "e"), ("notes", "NOTES", 520, "w"),
        ], height=13)
        for row in self.db.list_expenses():
            expense_table.insert("", "end", values=(
                row["expense_date"], row["category"], money(row["amount_paise"]), row["notes"] or "—",
            ))

    def expense_dialog(self) -> None:
        dialog = Modal(self, "Add society expense", 560, 480)
        items = [("Date", date.today().isoformat()), ("Category", "Maintenance"), ("Amount", "0"), ("Notes", "")]
        entries: list[ctk.CTkEntry] = []
        for index, (label, value) in enumerate(items):
            self.form_label(dialog.body, label, index)
            entry = self.form_entry(dialog.body, index, "Optional" if label == "Notes" else value)
            if value:
                entry.insert(0, value)
            entries.append(entry)

        def save() -> None:
            try:
                self.db.add_expense(entries[0].get(), entries[1].get(),
                                    parse_amount(entries[2].get()), entries[3].get())
                dialog.destroy()
                self.navigate("cashbook", self.show_cashbook)
            except Exception as exc:
                messagebox.showerror("Cannot add expense", str(exc), parent=dialog)
        self.modal_buttons(dialog, "Save expense", save)

    def show_reports(self) -> None:
        self.clear()
        self.page_header("Reports & backup", "Generate printable records and protect the local database.")
        grid = ctk.CTkFrame(self.content, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        grid.grid_columnconfigure((0, 1), weight=1, uniform="report")
        report_card = self.feature_card(grid, "▤", BLUE_SOFT, BLUE, "Monthly reports",
                                        "Create due-list PDFs and spreadsheet-compatible CSV exports.")
        report_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        backup_card = self.feature_card(grid, "↻", TEAL_SOFT, TEAL, "Database protection",
                                        "Create a complete backup before major changes or every month.")
        backup_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        periods = self.db.list_periods()
        choices = {f"{MONTHS[row['month'] - 1]} {row['year']}": row["id"] for row in periods}
        selected = tk.StringVar(value=next(iter(choices), ""))
        combo = ctk.CTkComboBox(report_card, variable=selected, values=list(choices), width=260,
                                height=40, border_color=BORDER, fg_color=SURFACE,
                                button_color=PRIMARY, button_hover_color=PRIMARY_HOVER)
        combo.pack(anchor="w", padx=22, pady=(18, 8))
        self.button(report_card, "Create PDF", lambda: self.make_due_report(choices.get(selected.get())),
                    "primary", 130).pack(anchor="w", padx=22, pady=5)
        self.button(report_card, "Export CSV", lambda: self.make_csv(choices.get(selected.get())),
                    "secondary", 130).pack(anchor="w", padx=22, pady=5)
        self.button(report_card, "Open reports folder", lambda: os.startfile(self.db.reports_dir),
                    "secondary", 150).pack(anchor="w", padx=22, pady=(18, 22))  # type: ignore[attr-defined]
        self.button(backup_card, "Create backup now", self.create_backup,
                    "success", 150).pack(anchor="w", padx=22, pady=(18, 5))
        self.button(backup_card, "Restore backup", self.restore_backup,
                    "secondary", 150).pack(anchor="w", padx=22, pady=5)
        self.button(backup_card, "Open backup folder", lambda: os.startfile(self.db.backups_dir),
                    "secondary", 150).pack(anchor="w", padx=22, pady=(18, 10))  # type: ignore[attr-defined]
        ctk.CTkLabel(backup_card, text=f"Local database\n{self.db.path}", text_color=MUTED,
                     justify="left", wraplength=430, font=(FONT, 8)).pack(anchor="w", padx=22, pady=(8, 22))

    def feature_card(self, parent, icon: str, icon_bg: str, icon_color: str,
                     title: str, subtitle: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14,
                            border_width=1, border_color=BORDER)
        ctk.CTkLabel(card, text=icon, width=44, height=44, corner_radius=12,
                     fg_color=icon_bg, text_color=icon_color,
                     font=(FONT_MEDIUM, 18)).pack(anchor="w", padx=22, pady=(22, 12))
        ctk.CTkLabel(card, text=title, text_color=TEXT,
                     font=(FONT_MEDIUM, 17)).pack(anchor="w", padx=22)
        ctk.CTkLabel(card, text=subtitle, text_color=TEXT_SECONDARY, wraplength=430,
                     justify="left", font=(FONT, 9)).pack(anchor="w", padx=22, pady=(5, 0))
        return card

    def create_backup(self) -> None:
        try:
            target = self.db.backup()
            messagebox.showinfo("Backup created", f"Saved to:\n{target}", parent=self)
        except Exception as exc:
            messagebox.showerror("Backup failed", str(exc), parent=self)

    def restore_backup(self) -> None:
        source = filedialog.askopenfilename(
            parent=self, title="Select database backup",
            filetypes=[("Database backup", "*.db"), ("All files", "*.*")],
        )
        if not source:
            return
        if not messagebox.askyesno(
            "Restore backup", "Replace current data with this backup? A safety copy will be created first.",
            icon="warning", parent=self,
        ):
            return
        try:
            self.db.restore(Path(source))
            messagebox.showinfo("Restore complete", "The backup was restored successfully.", parent=self)
            self.navigate("dashboard", self.show_dashboard)
        except Exception as exc:
            messagebox.showerror("Restore failed", str(exc), parent=self)

    def show_settings(self) -> None:
        self.clear()
        self.page_header("Settings", "Configure identity and defaults used for future records.")
        card = ctk.CTkFrame(self.content, fg_color=SURFACE, corner_radius=14,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x")
        title = ctk.CTkFrame(card, fg_color="transparent")
        title.pack(fill="x", padx=22, pady=(20, 10))
        ctk.CTkLabel(title, text="Society preferences", text_color=TEXT,
                     font=(FONT_MEDIUM, 15)).pack(anchor="w")
        ctk.CTkLabel(title, text="Changes apply only to newly created loans and periods.",
                     text_color=MUTED, font=(FONT, 8)).pack(anchor="w", pady=(3, 0))
        form = ctk.CTkFrame(card, fg_color="transparent")
        form.pack(fill="x", padx=22, pady=(0, 18))
        form.grid_columnconfigure(1, weight=1)
        settings = [
            ("society_name", "Society name", self.db.setting("society_name")),
            ("group_name", "Group name", self.db.setting("group_name")),
            ("monthly_contribution", "Default monthly contribution", f"{from_paise(int(self.db.setting('monthly_contribution', '50000'))):.2f}"),
            ("default_emi", "Default loan EMI", f"{from_paise(int(self.db.setting('default_emi', '100000'))):.2f}"),
            ("monthly_interest_bp", "Default monthly interest %", f"{int(self.db.setting('monthly_interest_bp', '150')) / 100:.2f}"),
        ]
        entries: dict[str, ctk.CTkEntry] = {}
        for index, (key, label, value) in enumerate(settings):
            self.form_label(form, label, index)
            entry = self.form_entry(form, index, "")
            entry.insert(0, value)
            entries[key] = entry

        def save() -> None:
            try:
                self.db.save_settings({
                    "society_name": entries["society_name"].get().strip(),
                    "group_name": entries["group_name"].get().strip(),
                    "monthly_contribution": str(round(parse_amount(entries["monthly_contribution"].get()) * 100)),
                    "default_emi": str(round(parse_amount(entries["default_emi"].get()) * 100)),
                    "monthly_interest_bp": str(round(parse_amount(entries["monthly_interest_bp"].get()) * 100)),
                })
                messagebox.showinfo("Settings saved", "Defaults updated successfully.", parent=self)
            except Exception as exc:
                messagebox.showerror("Cannot save settings", str(exc), parent=self)
        self.button(card, "Save changes", save, "primary", 130).pack(anchor="e", padx=22, pady=(0, 22))

    def form_label(self, parent, text: str, row: int) -> None:
        ctk.CTkLabel(parent, text=text, text_color=TEXT_SECONDARY,
                     font=(FONT_MEDIUM, 9)).grid(row=row, column=0, sticky="w", padx=(4, 8), pady=8)

    def form_entry(self, parent, row: int, placeholder: str) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(
            parent, placeholder_text=placeholder, height=38, corner_radius=8,
            border_color=BORDER, fg_color=SURFACE, text_color=TEXT,
        )
        entry.grid(row=row, column=1, sticky="ew", padx=(14, 4), pady=6)
        return entry

    def modal_buttons(
        self, dialog: Modal, text: str, command, width: int = 130, variant: str = "primary",
    ) -> None:
        self.button(dialog.buttons, text, command, variant, width).pack(side="right", padx=(8, 20), pady=16)
        self.button(dialog.buttons, "Cancel", dialog.destroy, "secondary", 90).pack(side="right", pady=16)


def run() -> None:
    ModernSocietyApp().mainloop()

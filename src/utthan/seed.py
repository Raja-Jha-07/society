"""Opening balances transcribed from Due List August.pdf.

The PDF is a point-in-time due list, not a transaction ledger. These values are
therefore imported as opening balances for August 2026 and remain auditable.
"""

OPENING_PERIOD = (2026, 8)
OPENING_CONTRIBUTION = 26_500.0
MONTHLY_CONTRIBUTION = 500.0
MONTHLY_INTEREST_RATE = 1.5
DEFAULT_EMI = 1_000.0
PREVIOUS_INTEREST = 148_085.0
OPENING_MAINTENANCE_EXPENSE = 500.0

# number, name, outstanding loan, lifetime loan amount, loan kind, last loan month,
# old due, late fee
OPENING_MEMBERS = [
    (1, "Aakash Kamat", 0, 0, "", "", 0, 0),
    (2, "Abhimanu Pandit", 39000, 95000, "Top-up", "2025-08", 0, 0),
    (3, "Abhinav Kumar", 32000, 50000, "Fresh", "2025-01", 0, 0),
    (4, "Abhinav Kumar-2", 0, 0, "", "", 0, 0),
    (5, "Ajit Mandal", 47000, 75000, "Top-up", "2025-07", 0, 0),
    (6, "Amar Pandit", 0, 30000, "Top-up", "2023-07", 0, 0),
    (7, "Amit Kamat", 0, 30000, "Fresh", "2025-09", 0, 0),
    (8, "Ankit Pandit", 0, 0, "", "", 0, 0),
    (9, "Arjun Pandit", 37000, 80000, "Top-up", "2025-06", 0, 0),
    (10, "Bablu Pandit", 0, 10000, "Fresh", "2025-01", 0, 0),
    (11, "Bachchan Pandit", 0, 0, "", "", 0, 0),
    (12, "Balram Pandit", 0, 0, "", "", 0, 0),
    (13, "Bechan Pandit", 40000, 67000, "Top-up", "2026-05", 0, 0),
    (14, "Bechan Pandit-2", 0, 0, "Substitute", "", 0, 0),
    (15, "Brijmohan Kamat", 36000, 64000, "Top-up", "2025-05", 0, 0),
    (16, "Chandan Kumar", 18000, 30000, "Fresh", "2025-07", 0, 0),
    (17, "Ch. Shekhar Kamat", 33000, 50000, "Fresh", "2025-02", 0, 0),
    (18, "Gagan Kamat", 32000, 50000, "Fresh", "2025-01", 0, 0),
    (19, "Gagan Kamat-2", 34000, 50000, "Fresh", "2025-03", 0, 0),
    (20, "Golu Pandit", 0, 0, "", "", 0, 0),
    (21, "Govind Pandit", 30000, 50000, "Fresh", "2024-11", 0, 0),
    (22, "Jai Shankar Pandit", 50000, 80000, "Top-up", "2025-04", 0, 0),
    (23, "Kailash Kamat", 40000, 55000, "Top-up", "2026-05", 0, 0),
    (24, "Kailash Kamat-2", 43000, 50000, "Fresh", "2025-12", 0, 0),
    (25, "Kailash Kamat-3", 0, 0, "", "", 0, 0),
    (26, "Kailash Pandit", 0, 40000, "Top-up", "2025-10", 0, 0),
    (27, "Kishan Pandit", 0, 0, "", "", 0, 0),
    (28, "Laxman K Pandit", 0, 25000, "Fresh", "2024-04", 0, 0),
    (29, "Madan Pandit", 11000, 25000, "Fresh", "2025-06", 0, 0),
    (30, "Madan Pandit - 2", 41000, 50000, "Fresh", "2025-10", 0, 0),
    (31, "Manav Kumar", 43000, 75000, "Fresh", "2025-12", 0, 0),
    (32, "Manish Mandal", 3000, 35000, "Fresh", "2023-11", 3235, 0),
    (33, "Manoj Kamat", 38000, 50000, "Top-up", "2026-05", 0, 0),
    (34, "Manoj Mandal", 22000, 65000, "Fresh", "2025-04", 0, 0),
    (35, "Mantu Chaudhary", 19000, 30000, "Fresh", "2025-08", 0, 0),
    (36, "Mukesh Pandit", 3000, 30000, "Fresh", "2024-04", 0, 0),
    (37, "Pachkauri Pandit", 3000, 30000, "Fresh", "2024-04", 0, 0),
    (38, "Priyanshu Kumar", 47000, 57000, "Top-up", "2026-06", 0, 0),
    (39, "Pulkit Kamat", 0, 0, "", "", 0, 0),
    (40, "Rajan Chaudhary", 11000, 30000, "Fresh", "2025-07", 0, 0),
    (41, "Rajdev Mandal", 40000, 80000, "Top-up", "2025-02", 0, 0),
    (42, "Raju Kamat", 0, 0, "", "", 0, 0),
    (43, "Ram Pandit", 49000, 75000, "Fresh", "2026-06", 0, 0),
    (44, "Ravi Kamat", 0, 0, "", "", 0, 0),
    (45, "Rohit Chaudhary", 43000, 80000, "Top-up", "2025-12", 0, 0),
    (46, "Sanjay Pandit", 0, 0, "", "", 0, 0),
    (47, "Sanjeev Pandit", 30000, 50000, "Fresh", "2024-11", 0, 0),
    (48, "Shankar Kamat", 29000, 70000, "Top-up", "2025-08", 0, 0),
    (49, "Shiv Chandra Kamat", 0, 0, "", "", 0, 0),
    (50, "Shiv Kumar Pandit", 3000, 30000, "Fresh", "2024-04", 0, 0),
    (51, "Shrikant Kamat", 0, 0, "", "", 0, 0),
    (52, "Siddharth Kumar", 17000, 20000, "Fresh", "2026-05", 3795, 270),
    (53, "Sonu Mandal", 3000, 35000, "Fresh", "2023-11", 0, 0),
    (54, "Sujit Yadav", 45000, 60000, "Top-up", "2025-03", 0, 0),
    (55, "Sumit Kumar", 0, 0, "", "", 0, 0),
    (56, "Suraj Kumar-I", 10000, 55000, "Fresh", "2025-04", 0, 0),
    (57, "Suraj Kumar-2", 0, 0, "", "", 0, 0),
    (58, "Vikash Yadav", 9000, 50000, "Fresh", "2026-05", 0, 0),
    (59, "Vishnu Mandal", 47000, 65000, "Top-up", "2025-05", 0, 0),
    (60, "Yash Kumar", 0, 0, "", "", 0, 0),
]

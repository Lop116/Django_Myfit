"""Create demo data so every dashboard has something to show.

    python manage.py seed_demo_data
    python manage.py seed_demo_data --password "SomethingElse1!"

Safe to run more than once (existing rows are reused). Demo accounts only:
refuses to run when DEBUG is off unless --force is given.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.membership_services import assign_membership, check_in_membership
from core.models import (
    Branch,
    ClassSession,
    ClientMembership,
    ClientProfile,
    CoachClientAssignment,
    CoachProfile,
    CoachSpecialty,
    MembershipChangeRequest,
    MembershipPlan,
    SupportTicket,
    WorkoutLog,
)
from core.services import book_client_into_class

User = get_user_model()


class Command(BaseCommand):
    help = "Create demo admin, coaches, clients, plans, memberships, classes and bookings."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="DemoPass123!", help="Password for all demo accounts.")
        parser.add_argument("--force", action="store_true", help="Allow running when DEBUG is False.")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to create demo accounts while DEBUG is off (use --force).")
        self.password = options["password"]
        today = timezone.localdate()

        groups = {name: Group.objects.get_or_create(name=name)[0] for name in ("Client", "Coach", "Admin")}

        admin = self.user("demo_admin", "Admin", "Demo", groups["Admin"], is_staff=True, is_superuser=True)

        port_louis, _ = Branch.objects.get_or_create(
            name="Port Louis Central", defaults={"address": "Royal Road, Port Louis", "phone": "2100001"})
        ebene, _ = Branch.objects.get_or_create(
            name="Ebène Fitness", defaults={"address": "Cybercity, Ebène", "phone": "4650002"})

        specialties = {n: CoachSpecialty.objects.get_or_create(name=n)[0] for n in ("Strength", "Yoga", "Cardio")}

        coaches = []
        for i, (branch, picks) in enumerate(((port_louis, ("Strength", "Cardio")), (ebene, ("Yoga",))), start=1):
            user = self.user(f"demo_coach{i}", "Coach", f"Coach{i}", groups["Coach"])
            profile, _ = CoachProfile.objects.get_or_create(user=user, defaults={"branch": branch})
            profile.specialties.set([specialties[p] for p in picks])
            coaches.append(profile)

        clients = []
        for i in range(1, 6):
            user = self.user(f"demo_client{i}", "Client", f"Client{i}", groups["Client"])
            profile, _ = ClientProfile.objects.get_or_create(user=user, defaults={"phone": f"57000{i:02d}"})
            clients.append(profile)

        plans = {}
        for name, price, days in (("Monthly", "1500.00", 30), ("Quarterly", "4000.00", 90), ("Annual", "14000.00", 365)):
            plans[name], _ = MembershipPlan.objects.get_or_create(
                name=name, defaults={"price": price, "duration_days": days, "benefits": f"{name} access"})

        # client1/2 active, client3 lapsed (dates in the past), client4 starts next week, client5 has none.
        starts = {0: -5, 1: -2, 2: -60, 3: 7}
        for index, offset in starts.items():
            user = clients[index].user
            if not ClientMembership.objects.filter(user=user).exists():
                assign_membership(user, plans["Monthly"], today + timedelta(days=offset))

        first = ClientMembership.objects.filter(user=clients[0].user).first()
        if first and not MembershipChangeRequest.objects.filter(membership=first).exists():
            MembershipChangeRequest.objects.create(
                membership=first, requested_plan=plans["Quarterly"], reason="Training for a race.")
            try:
                check_in_membership(first.pk)
            except ValidationError:
                pass  # already checked in from a previous run

        sessions = []
        for n, (title, coach, branch) in enumerate((("Morning Yoga", coaches[1], ebene),
                                                    ("Strength Circuit", coaches[0], port_louis),
                                                    ("Cardio Blast", coaches[0], port_louis)), start=1):
            session, _ = ClassSession.objects.get_or_create(
                title=title, date=today + timedelta(days=n),
                defaults={"branch": branch, "coach": coach, "time": "07:30", "capacity": 2})
            sessions.append(session)

        # Capacity 2: book clients 1 and 2 into the first class; they fill it.
        for client in clients[:2]:
            try:
                book_client_into_class(sessions[0].pk, client)
            except ValidationError:
                pass  # already booked

        for client in clients[:2]:
            CoachClientAssignment.objects.get_or_create(client=client, defaults={"coach": coaches[0]})

        if not SupportTicket.objects.filter(subject="Demo: locker key").exists():
            SupportTicket.objects.create(
                user=clients[0].user, kind="ticket", name="Client1", email=clients[0].user.email,
                topic="Facilities", subject="Demo: locker key", message="I lost my locker key.")

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready. Log in as demo_admin / demo_coach1 / demo_client1 with password: {self.password}"))

    def user(self, username, role, first_name, group, **extra):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"first_name": first_name, "email": f"{username}@example.com", **extra},
        )
        if created:
            user.set_password(self.password)
            user.save()
        user.groups.add(group)
        return user

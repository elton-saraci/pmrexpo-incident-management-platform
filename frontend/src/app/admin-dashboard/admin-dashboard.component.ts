import { Component, OnInit } from '@angular/core';
import { NgIf, NgForOf, NgClass, DatePipe } from '@angular/common'; // ⬅️ add DatePipe


import {
  AdminDataService,
  FireDepartment,
  Incident,
} from '../admin-data.service';
import { JsmapComponent } from '../jsmap/jsmap';

@Component({
  selector: 'app-admin-dashboard',
  standalone: true,
  templateUrl: './admin-dashboard.component.html',
  styleUrls: ['./admin-dashboard.component.scss'],
  imports: [NgIf, NgForOf, NgClass, DatePipe, JsmapComponent],
})
export class AdminDashboardComponent implements OnInit {
  referenceLat!: number;
  referenceLng!: number;

  fireDepartments: FireDepartment[] = [];
  incidents: Incident[] = [];

  isLoading = true;
  lastUpdated?: Date;

  constructor(private dataService: AdminDataService) {}

  ngOnInit(): void {
    // now dataService is definitely initialised
    this.referenceLat = this.dataService.referenceLat;
    this.referenceLng = this.dataService.referenceLng;

    this.loadData();
  }

  refresh(): void {
    this.loadData();
    this.pending = 2;
  }

  private loadData(): void {
    this.isLoading = true;

    // Fire departments
    this.dataService
      .getFireDepartmentsNear(this.referenceLat, this.referenceLng)
      .subscribe({
        next: (fds) => {
          this.fireDepartments = fds;
          this.checkDone();
        },
        error: () => this.checkDone(),
      });

    // Incidents
    this.dataService
      .getIncidentsNear(this.referenceLat, this.referenceLng)
      .subscribe({
        next: (incidents) => {
          this.incidents = incidents;
          this.checkDone();
        },
        error: () => this.checkDone(),
      });
  }

  private pending = 2;
  private checkDone(): void {
    this.pending -= 1;
    if (this.pending <= 0) {
      this.isLoading = false;
      this.pending = 2;
      this.lastUpdated = new Date();
    }
  }

  isOccupied(fd: FireDepartment): boolean {
    return fd.available_responders <= 0;
  }

  distanceFromRef(fd: FireDepartment): number {
    return this.dataService.distanceKm(
      this.referenceLat,
      this.referenceLng,
      fd.location.latitude,
      fd.location.longitude
    );
  }
}

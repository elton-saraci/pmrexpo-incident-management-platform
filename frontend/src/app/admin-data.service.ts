// src/app/admin-data.service.ts
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { catchError, map, of, Observable } from 'rxjs';

// --- Domain models ---

export interface FireDepartment {
  id: string;
  name: string;
  location: {
    latitude: number;
    longitude: number;
  };
  available_responders: number;
}

export interface Incident {
  id?: string;
  type: string;               // forest_fire, blackout, flood, ...
  latitude: number;
  longitude: number;
  description?: string;
  severity_score?: number;    // optional, but useful if you have it
}

// --- Service ---

@Injectable({ providedIn: 'root' })
export class AdminDataService {
  private readonly baseUrl = 'http://localhost:8080/api';

  // Koelnmesse reference location
  readonly referenceLat = 50.947086;
  readonly referenceLng = 6.982777;

  constructor(private http: HttpClient) {}

  getFireDepartmentsNear(
    lat: number = this.referenceLat,
    lng: number = this.referenceLng,
    radiusKm: number = 300
  ): Observable<FireDepartment[]> {
    // If your backend later accepts query params, you can add them here.
    return this.http
      .get<FireDepartment[]>(`${this.baseUrl}/fire-departments`)
      .pipe(
        map((items) => items ?? []),
        catchError((err) => {
          console.warn('Fire departments API failed – using mock data.', err);
          return of(this.getMockFireDepartments());
        })
      );
  }

  getIncidentsNear(
    lat: number = this.referenceLat,
    lng: number = this.referenceLng,
    radiusKm: number = 300
  ): Observable<Incident[]> {
    return this.http
      .get<Incident[]>(`${this.baseUrl}/incidents`)
      .pipe(
        map((items) => items ?? []),
        catchError((err) => {
          console.warn('Incidents API failed – using mock data.', err);
          return of(this.getMockIncidents());
        })
      );
  }

  // --- Mock data around Köln Messe ---

  private getMockFireDepartments(): FireDepartment[] {
    return [
      {
        id: 'FD-001',
        name: 'Köln Innenstadt Fire Station',
        location: {
          latitude: 50.9382,
          longitude: 6.9599,
        },
        available_responders: 9,
      },
      {
        id: 'FD-002',
        name: 'Köln-Deutz Fire Station',
        location: {
          latitude: 50.9409,
          longitude: 6.9793,
        },
        available_responders: 0, // occupied
      },
      {
        id: 'FD-003',
        name: 'Köln-Mülheim Fire Station',
        location: {
          latitude: 50.969,
          longitude: 7.0,
        },
        available_responders: 4,
      },
      {
        id: 'FD-004',
        name: 'Köln-Ehrenfeld Fire Station',
        location: {
          latitude: 50.9495,
          longitude: 6.9083,
        },
        available_responders: 2,
      },
    ];
  }

  private getMockIncidents(): Incident[] {
    return [
      {
        id: 'INC-001',
        type: 'forest_fire',
        latitude: 50.9485,
        longitude: 6.9820,
        severity_score: 3,
        description: 'Vegetation fire reported near Rheinpark.',
      },
      {
        id: 'INC-002',
        type: 'flood',
        latitude: 50.939,
        longitude: 6.975,
        severity_score: 4,
        description: 'Localized flooding near Deutz harbour.',
      },
    ];
  }

  // optional helper for distance displays
  distanceKm(
    lat1: number,
    lng1: number,
    lat2: number,
    lng2: number
  ): number {
    const toRad = (deg: number) => (deg * Math.PI) / 180;
    const R = 6371; // km
    const dLat = toRad(lat2 - lat1);
    const dLng = toRad(lng2 - lng1);
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(toRad(lat1)) *
        Math.cos(toRad(lat2)) *
        Math.sin(dLng / 2) *
        Math.sin(dLng / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return Math.round(R * c * 10) / 10; // one decimal
  }
}

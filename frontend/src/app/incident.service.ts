// src/app/incident.service.ts
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface IncidentReport {
  type: 'forest_fire' | 'flood' | 'blackout';
  latitude: number;
  longitude: number;
  severity_score: number; // 1–5
}

@Injectable({ providedIn: 'root' })
export class IncidentService {
  private readonly baseUrl = 'http://localhost:8080/api/incidents';

  constructor(private http: HttpClient) {}

  reportIncident(report: IncidentReport): Observable<any> {
    return this.http.post(`${this.baseUrl}/report`, report);
  }
}

// src/app/sensor-component/sensor-component.ts
import { Component } from '@angular/core';
import {
  NgIf,
  NgForOf,
  NgClass,
  JsonPipe,
} from '@angular/common';

import { IncidentService, IncidentReport } from '../incident.service';

type DisasterType = 'forest_fire' | 'flood' | 'blackout';

interface SeverityOption {
  id: 'small' | 'medium' | 'big';
  label: string;
  score: number; // 1–5
  description: string;
}

interface DisasterScenario {
  type: DisasterType;
  label: string;
  icon: string;
  accentClass: string;
  description: string;
  severityOptions: SeverityOption[];
}

@Component({
  selector: 'app-sensor-component',
  standalone: true,                              // ⬅️ standalone component
  templateUrl: './sensor-component.html',
  styleUrls: ['./sensor-component.scss'],
  imports: [                                     // ⬅️ add all used directives/pipes
    NgIf,
    NgForOf,
    NgClass,
    JsonPipe,
  ],
})
export class SensorComponent {
  // Köln Messe coordinates
  readonly latitude = 50.947086;
  readonly longitude = 6.982777;

  isSending = false;
  lastStatus: 'idle' | 'success' | 'error' = 'idle';
  lastMessage = '';
  lastPayload?: IncidentReport;

  disasters: DisasterScenario[] = [
    {
      type: 'forest_fire',
      label: 'Forest Fire',
      icon: '🔥',
      accentClass: 'fire',
      description:
        'Simulate a wildfire near Köln Messe – from a small ignition to a major blaze.',
      severityOptions: [
        {
          id: 'small',
          label: 'Small Fire',
          score: 1,
          description: 'Local ignition, quickly detectable, low impact.',
        },
        {
          id: 'medium',
          label: 'Growing Fire',
          score: 3,
          description: 'Spreading flames, risk for nearby infrastructure.',
        },
        {
          id: 'big',
          label: 'Major Wildfire',
          score: 5,
          description: 'Critical situation, multi-agency response required.',
        },
      ],
    },
    {
      type: 'flood',
      label: 'Flood',
      icon: '🌊',
      accentClass: 'flood',
      description:
        'Simulate flooding of the surrounding area and infrastructure.',
      severityOptions: [
        {
          id: 'small',
          label: 'High Water',
          score: 1,
          description: 'Localized water accumulation.',
        },
        {
          id: 'medium',
          label: 'Street Flood',
          score: 3,
          description: 'Roads affected, access limited.',
        },
        {
          id: 'big',
          label: 'Severe Flood',
          score: 5,
          description: 'Wide-area flooding, major disruption.',
        },
      ],
    },
    {
      type: 'blackout',
      label: 'Blackout',
      icon: '💡',
      accentClass: 'blackout',
      description:
        'Simulate partial to full power outage around the venue.',
      severityOptions: [
        {
          id: 'small',
          label: 'Local Outage',
          score: 1,
          description: 'Single building affected.',
        },
        {
          id: 'medium',
          label: 'District Outage',
          score: 3,
          description: 'Multiple halls / blocks offline.',
        },
        {
          id: 'big',
          label: 'Citywide Outage',
          score: 5,
          description: 'Massive power loss, critical impact.',
        },
      ],
    },
  ];

  constructor(private incidentService: IncidentService) {}

  simulate(disaster: DisasterScenario, severity: SeverityOption): void {
    if (this.isSending) {
      return;
    }

    const payload: IncidentReport = {
      type: disaster.type,
      latitude: this.latitude,
      longitude: this.longitude,
      severity_score: severity.score,
    };

    this.isSending = true;
    this.lastStatus = 'idle';
    this.lastMessage = '';

    this.incidentService.reportIncident(payload).subscribe({
      next: () => {
        this.isSending = false;
        this.lastStatus = 'success';
        this.lastPayload = payload;
        this.lastMessage = `${severity.label} ${disaster.label} simulation sent successfully.`;
      },
      error: (err) => {
        console.error('Simulation failed', err);
        this.isSending = false;
        this.lastStatus = 'error';
        this.lastPayload = payload;
        this.lastMessage =
          'Failed to send simulation. Please check the backend or network.';
      },
    });
  }
}

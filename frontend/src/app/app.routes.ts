import { Routes } from '@angular/router';
import { JsmapComponent } from './jsmap/jsmap';
import { UserComponent } from './user-component/user-component';
import { SensorComponent } from './sensor-component/sensor-component';
import { AdminDashboardComponent } from './admin-dashboard/admin-dashboard.component';


export const routes: Routes = [
    {
        path: '',
        component: UserComponent,
    },
    {
        path: 'user',
        component: UserComponent,
    },
    {
        path: 'sensors',
        component: SensorComponent,
    },
    { path: 'admin',
     component: AdminDashboardComponent
     },
];

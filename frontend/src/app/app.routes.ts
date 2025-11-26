import { Routes } from '@angular/router';
import { JsmapComponent } from './jsmap/jsmap';
import { UserComponent } from './user-component/user-component';

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
        path: 'admin',
        component: JsmapComponent,
    },
];

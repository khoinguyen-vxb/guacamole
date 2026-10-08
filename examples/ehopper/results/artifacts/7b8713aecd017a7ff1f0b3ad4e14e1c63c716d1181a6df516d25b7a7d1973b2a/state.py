class State:
    def __init__(self, x, y, z, u, v, w, q0, q1, q2, q3, p, q, r):
        self.x = x
        self.y = y
        self.z = z
        self.u = u
        self.v = v
        self.w = w
        self.q0 = q0
        self.q1 = q1
        self.q2 = q2
        self.q3 = q3
        self.p = p
        self.q = q
        self.r = r

        self.x_arr = []
        self.y_arr = []
        self.z_arr = []
        self.u_arr = []
        self.v_arr = []
        self.w_arr = []
        self.q0_arr = []
        self.q1_arr = []
        self.q2_arr = []
        self.q3_arr = []
        self.p_arr = []
        self.q_arr = []
        self.r_arr = []

    def update_state(self, x, y, z, u, v, w, q0, q1, q2, q3, p, q, r):
        self.x_arr.append(x)
        self.y_arr.append(y)
        self.z_arr.append(z)
        self.u_arr.append(u)
        self.v_arr.append(v)
        self.w_arr.append(w)
        self.q0_arr.append(q0)
        self.q1_arr.append(q1)
        self.q2_arr.append(q2)
        self.q3_arr.append(q3)
        self.p_arr.append(p)
        self.q_arr.append(q)
        self.r_arr.append(r)

        self.x = x
        self.y = y
        self.z = z
        self.u = u
        self.v = v
        self.w = w
        self.q0 = q0
        self.q1 = q1
        self.q2 = q2
        self.q3 = q3
        self.p = p
        self.q = q
        self.r = r

    def unpack_state(self):
        return (
            self.x,
            self.y,
            self.z,
            self.u,
            self.v,
            self.w,
            self.q0,
            self.q1,
            self.q2,
            self.q3,
            self.p,
            self.q,
            self.r,
        )

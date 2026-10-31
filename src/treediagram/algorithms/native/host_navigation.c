/* Bounded mathematical bridge. Caller owns each context and scratch workspace.
 * kind: 0 INS, 1 SF6, 2 KF6, 3 ESKF15, 4 ESKF20, 5 InEKF15, 6 InEKF20.
 * All simulated samples are body specific force and angular rate, SI/ENU.
 * No truth pose is admitted after explicit initialization. */
#include "ins_mechanization.h"
#include "navigation_kf.h"
#include "navigation_sf6.h"
#include "navigation_eskf.h"
#include "navigation_bounded.h"
#include "attitude_frame.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

typedef enum { HOST_OK = 0, HOST_WAITING, HOST_INVALID, HOST_STALE,
    HOST_REJECTED, HOST_NUMERIC, HOST_UNSUPPORTED } HostNavigationResult;

typedef struct
{
    int kind;
    uint64_t timestamp_us, gnss_timestamp_us;
    uint8_t started, gnss_seen;
    float gravity, previous_accel[3], previous_gyro[3];
    InsMechanizationContext ins;
    InsState increment;
    NavigationKfContext kf;
    NavigationSf6Context sf;
    NavigationEskfState eskf;
    NavigationEskfWorkspace eskf_work;
    NavigationEskfConfig eskf_config;
    NavigationState augmented;
    NavigationWorkspace augmented_work;
    double density[12];
    double magnetic_installation[9], magnetic_inclination, magnetic_declination, magnetic_strength;
    uint64_t barometer_timestamp_us, magnetic_timestamp_us;
    uint8_t barometer_seen, magnetic_seen;
    double output[13]; /* p3 v3 q4 measured angular rate3 */
} HostNavigationContext;

size_t HostNavigation_ContextSize(void) { return sizeof(HostNavigationContext); }

static uint8_t HostNavigation_VectorValid(const double *values, unsigned count)
{
    unsigned index;
    if ((values == NULL) || (count > 16U)) { return 0U; }
    for (index = 0U; index < count; ++index)
    { if (!isfinite(values[index]) || fabs(values[index]) > 1.0e15) { return 0U; } }
    return 1U;
}

static uint8_t HostNavigation_QuaternionMatrix(const double q[4], double matrix[9])
{
    double norm,w,x,y,z;
    norm=hypot(hypot(q[0],q[1]),hypot(q[2],q[3]));
    if(!isfinite(norm) || norm<1.0e-12) { return 0U; }
    w=q[0]/norm;x=q[1]/norm;y=q[2]/norm;z=q[3]/norm;
    /* Preserve the bounded double kernel's SO(3) contract. A float32 matrix
     * promoted to double is not sufficiently orthonormal for that contract. */
    matrix[0]=1.0-2.0*(y*y+z*z); matrix[1]=2.0*(x*y-z*w); matrix[2]=2.0*(x*z+y*w);
    matrix[3]=2.0*(x*y+z*w); matrix[4]=1.0-2.0*(x*x+z*z); matrix[5]=2.0*(y*z-x*w);
    matrix[6]=2.0*(x*z-y*w); matrix[7]=2.0*(y*z+x*w); matrix[8]=1.0-2.0*(x*x+y*y);
    return 1U;
}

HostNavigationResult HostNavigation_Init(void *memory, int kind,
    const double q_nb[4], double gravity)
{
    HostNavigationContext *context = memory;
    float q[4]; unsigned index;
    if ((context == NULL) || (kind < 0) || (kind > 6) ||
        (HostNavigation_VectorValid(q_nb, 4U) == 0U) ||
        !isfinite(gravity) || (gravity <= 0.0) || (gravity > 100.0))
    { return HOST_INVALID; }
    for (index = 0U; index < 4U; ++index) { q[index] = (float)q_nb[index]; }
    if (Attitude_QuaternionNormalize(q) == 0U) { return HOST_INVALID; }
    memset(context, 0, sizeof(*context));
    context->kind = kind; context->gravity = (float)gravity;
    InsMechanization_Init(&context->ins, (float)gravity);
    if (InsMechanization_ResetNavigationWithAttitude(&context->ins, q) == 0U)
    { return HOST_INVALID; }
    NavigationKf_Init(&context->kf);
    for (index = 0U; index < 4U; ++index) { context->output[index + 6U] = q[index]; }
    context->eskf_config = (NavigationEskfConfig){(float)gravity,
        0.001f, 0.05f, 0.00001f, 0.001f, {6.635f, 9.21f},
        {10.828f, 13.816f}, 4.0f, 0U};
    for (index = 0U; index < 12U; ++index)
    { context->density[index] = (index < 3U) ? 0.001 : (index < 6U) ? 0.05 : 0.00001; }
    return HOST_OK;
}

HostNavigationResult HostNavigation_MagneticPriorSet(void *memory,
    const double field_n_uT[3], const double q_bs[4])
{
    HostNavigationContext *context = memory;
    double horizontal, strength;
    if (context == NULL || context->started || !HostNavigation_VectorValid(field_n_uT,3U) ||
        !HostNavigation_VectorValid(q_bs,4U)) { return HOST_INVALID; }
    horizontal = hypot(field_n_uT[0],field_n_uT[1]); strength = hypot(horizontal,field_n_uT[2]);
    if (strength <= 0.0) { return HOST_INVALID; }
    if (!HostNavigation_QuaternionMatrix(q_bs,context->magnetic_installation)) { return HOST_INVALID; }
    context->magnetic_strength=strength;
    context->magnetic_inclination=atan2(-field_n_uT[2],horizontal);
    context->magnetic_declination=atan2(field_n_uT[0],field_n_uT[1]);
    return HOST_OK;
}

static HostNavigationResult HostNavigation_InitialEpoch(HostNavigationContext *context,
    uint64_t timestamp_us)
{
    float nominal[16] = {0.0f}, covariance[15][15] = {{0.0f}};
    const float sf_gain[6] = {0.2f, 0.2f, 0.2f, 0.1f, 0.1f, 0.1f};
    const float velocity[3] = {0.0f, 0.0f, 0.0f};
    double q[4]; unsigned index, dimension;
    for (index = 0U; index < 4U; ++index)
    { nominal[index + 6U] = (float)context->output[index + 6U]; q[index] = context->output[index + 6U]; }
    if (context->kind == 1 && NavigationSf6_Initialize(&context->sf, sf_gain, velocity,
        timestamp_us) != NAV_SF6_OK) { return HOST_INVALID; }
    if (context->kind == 3)
    {
        for (index = 0U; index < 15U; ++index)
        { covariance[index][index] = (index < 6U) ? 1.0f : 0.01f; }
        if (NavigationEskf_Initialize(&context->eskf, &context->eskf_work,
            nominal, covariance, timestamp_us, 1U, 1U) != NAV_ESKF_OK)
        { return HOST_INVALID; }
    }
    if (context->kind >= 4)
    {
        context->augmented.model = (NavigationModel)(context->kind - 3);
        if (!HostNavigation_QuaternionMatrix(q, context->augmented.rotation)) { return HOST_INVALID; }
        memcpy(context->augmented.installation,context->magnetic_installation,
            sizeof(context->augmented.installation));
        context->augmented.inclination = context->magnetic_inclination;
        context->augmented.declination = context->magnetic_declination;
        context->augmented.time_s = (double)timestamp_us * 1.0e-6;
        dimension = (context->kind == 5) ? 15U : 20U;
        for (index = 0U; index < dimension; ++index)
        { context->augmented.covariance[index * 20U + index] = 0.1; }
        if (Navigation_Validate(&context->augmented, &context->augmented_work) != NavigationOk)
        { return HOST_INVALID; }
    }
    return HOST_OK;
}

static HostNavigationResult HostNavigation_PredictExtended(HostNavigationContext *context,
    uint64_t timestamp_us, const double accel[3], const double gyro[3], double dt)
{
    unsigned index;
    if (context->kind == 3)
    {
        NavigationEskfBodyInput input = {0};
        input.start_us = context->timestamp_us; input.end_us = timestamp_us;
        input.dt_s = (float)dt; input.source = 1U; input.generation = 1U;
        for (index = 0U; index < 3U; ++index)
        {
            input.gyro_radps[0][index] = context->previous_gyro[index];
            input.accel_mps2[0][index] = context->previous_accel[index];
            input.gyro_radps[1][index] = (float)gyro[index];
            input.accel_mps2[1][index] = (float)accel[index];
        }
        NavigationEskfResult result = NavigationEskf_Predict(&context->eskf, &context->eskf_work,
            &context->eskf_config, &input);
        if (result != NAV_ESKF_OK)
        { return result == NAV_ESKF_INVALID_INPUT ? HOST_INVALID : HOST_NUMERIC; }
    }
    else
    {
        double density[12], mean_gyro[3], mean_accel[3];
        const double gravity[3] = {0.0, 0.0, -context->gravity};
        memcpy(density, context->density, sizeof(density));
        if (context->kind == 4)
        { for (index = 0U; index < 3U; ++index) { density[index] = 0.05; density[index + 3U] = 0.001; } }
        for (index = 0U; index < 3U; ++index)
        { mean_gyro[index] = 0.5 * (gyro[index] + context->previous_gyro[index]);
          mean_accel[index] = 0.5 * (accel[index] + context->previous_accel[index]); }
        /* Integer input clock owns the endpoint. Computing the interval from
         * that endpoint prevents repeated-addition drift in the double core. */
        double exact_dt = (double)timestamp_us * 1.0e-6 - context->augmented.time_s;
        if (Navigation_Predict(&context->augmented, &context->augmented_work,
            mean_gyro, mean_accel, gravity, density, exact_dt) != NavigationOk) { return HOST_NUMERIC; }
    }
    return HOST_OK;
}

static HostNavigationResult HostNavigation_OutputRefresh(HostNavigationContext *context)
{
    unsigned index;
    float q[4], matrix[3][3];
    for (index = 0U; index < 3U; ++index)
    {
        context->output[index] = context->kind == 0 ? context->increment.position_n_m[index] :
            context->kind == 1 ? context->sf.latest.state[index + 3U] :
            context->kind == 2 ? context->kf.state[index] :
            context->kind == 3 ? context->eskf.position[index] : context->augmented.position[index];
        context->output[index + 3U] = context->kind == 0 ? context->increment.velocity_n_mps[index] :
            context->kind == 1 ? context->sf.latest.state[index] :
            context->kind == 2 ? context->kf.state[index + 3U] :
            context->kind == 3 ? context->eskf.velocity[index] : context->augmented.velocity[index];
    }
    if (context->kind >= 4)
    {
        for (index = 0U; index < 9U; ++index)
        { matrix[index / 3U][index % 3U] = (float)context->augmented.rotation[index]; }
        if (Attitude_RotationMatrixToQuaternionWxyz(matrix, q) == 0U) { return HOST_NUMERIC; }
    }
    for (index = 0U; index < 4U; ++index)
    { context->output[index + 6U] = context->kind >= 4 ? q[index] :
        context->kind == 3 ? context->eskf.quaternion[index] : context->ins.q_nb_propagated[index]; }
    return HOST_OK;
}

HostNavigationResult HostNavigation_Imu(void *memory, uint64_t timestamp_us,
    const double accel[3], const double gyro[3], double output[13])
{
    HostNavigationContext *context = memory;
    HostNavigationResult result = HOST_WAITING;
    InsAlgorithmSample sample = {0}; unsigned index; double dt;
    if ((context == NULL) || (output == NULL) ||
        !HostNavigation_VectorValid(accel, 3U) || !HostNavigation_VectorValid(gyro, 3U))
    { return HOST_INVALID; }
    if (context->started && timestamp_us <= context->timestamp_us) { return HOST_STALE; }
    dt = context->started ? (double)(timestamp_us - context->timestamp_us) * 1.0e-6 : 0.0;
    if (dt > 0.02) { return HOST_STALE; }
    if (!context->started && HostNavigation_InitialEpoch(context, timestamp_us) != HOST_OK)
    { return HOST_INVALID; }
    if (context->kind < 3)
    {
        sample.timestamp_us = timestamp_us;
        sample.valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
        for (index = 0U; index < 3U; ++index)
        { sample.accel_b_mps2[index] = (float)accel[index]; sample.gyro_b_radps[index] = (float)gyro[index]; }
        if (InsMechanization_Update(&context->ins, &sample, &context->increment))
        {
            result = HOST_OK;
            if (context->kind == 2 && NavigationKf_PredictInterval(&context->kf,
                context->increment.delta_velocity_n_corrected, context->increment.dt_s,
                context->increment.dt_s) != NAV_KF_PREDICT_OK) { result = HOST_NUMERIC; }
            if (context->kind == 1 && NavigationSf6_Predict(&context->sf, timestamp_us,
                context->increment.delta_velocity_n_corrected, context->increment.dt_s) != NAV_SF6_OK)
            { result = HOST_NUMERIC; }
        }
    }
    else if (context->started)
    { result = HostNavigation_PredictExtended(context, timestamp_us, accel, gyro, dt); }
    if (result != HOST_OK && result != HOST_WAITING) { return result; }
    for (index = 0U; index < 3U; ++index)
    { context->previous_accel[index] = (float)accel[index]; context->previous_gyro[index] = (float)gyro[index];
      context->output[index + 10U] = gyro[index]; }
    context->timestamp_us = timestamp_us; context->started = 1U;
    if (result == HOST_OK) { result = HostNavigation_OutputRefresh(context); }
    memcpy(output, context->output, sizeof(context->output));
    return result;
}

HostNavigationResult HostNavigation_Gnss(void *memory, uint64_t measurement_us,
    uint64_t arrival_us, const double position[3], const double velocity[3],
    const double position_std[3], const double velocity_std[3])
{
    HostNavigationContext *context = memory;
    float p[3], v[3], pv[3], vv[3]; unsigned index, group;
    HostNavigationResult result = HOST_OK;
    if ((context == NULL) || !context->started ||
        !HostNavigation_VectorValid(position, 3U) || !HostNavigation_VectorValid(velocity, 3U) ||
        !HostNavigation_VectorValid(position_std, 3U) || !HostNavigation_VectorValid(velocity_std, 3U))
    { return HOST_INVALID; }
    if (measurement_us > arrival_us || arrival_us > context->timestamp_us ||
        (context->gnss_seen && measurement_us <= context->gnss_timestamp_us)) { return HOST_STALE; }
    /* Extended kernels require actual co-timed measurements. No timestamp relabelling. */
    if (context->kind >= 3 && measurement_us != context->timestamp_us) { return HOST_STALE; }
    for (index = 0U; index < 3U; ++index)
    {
        if (position_std[index] <= 0.0 || velocity_std[index] <= 0.0) { return HOST_INVALID; }
        p[index] = (float)position[index]; v[index] = (float)velocity[index];
        pv[index] = (float)(position_std[index] * position_std[index]);
        vv[index] = (float)(velocity_std[index] * velocity_std[index]);
    }
    if (context->kind == 2)
    {
        NavigationKfUpdateResult pr = NavigationKf_UpdateGnssPosition(&context->kf, p, pv);
        NavigationKfUpdateResult vr = NavigationKf_UpdateGnssVelocity3D(&context->kf, v, vv);
        if (pr > NAV_KF_UPDATE_SOFT_WEIGHTED || vr > NAV_KF_UPDATE_SOFT_WEIGHTED) { result = HOST_REJECTED; }
    }
    else if (context->kind == 1 || context->kind == 3)
    {
        for (group = 0U; group < 4U; ++group)
        {
            unsigned offset = (group & 1U) ? 2U : 0U;
            float *observation = group < 2U ? p : v;
            float *variance = group < 2U ? pv : vv;
            if (context->kind == 1)
            {
                NavigationSf6Measurement sample = {0}; uint64_t boundary;
                sample.measurement_us = measurement_us; sample.receive_us = arrival_us;
                sample.sequence = (uint32_t)(measurement_us / 1000U); sample.group = (uint8_t)group;
                sample.observation[0] = observation[offset];
                sample.observation[1] = (offset == 0U) ? observation[1] : 0.0f;
                if (NavigationSf6_Update(&context->sf, &sample, &boundary) != NAV_SF6_OK) { result = HOST_REJECTED; }
            }
            else
            {
                NavigationEskfMeasurement sample = {0}; NavigationEskfOutcome outcome;
                sample.group = (uint8_t)group; sample.physically_valid = 1U;
                sample.observation[0] = observation[offset]; sample.variance[0] = variance[offset];
                sample.observation[1] = (offset == 0U) ? observation[1] : 0.0f;
                sample.variance[1] = (offset == 0U) ? variance[1] : 1.0f;
                if (NavigationEskf_UpdateRevision2(&context->eskf, &context->eskf_work,
                    &context->eskf_config, &sample, &outcome) > NAV_ESKF_SOFT_WEIGHTED) { result = HOST_REJECTED; }
            }
        }
    }
    else if (context->kind >= 4)
    {
        double covariance[9] = {0.0}; NavigationResult pr, vr;
        for (index = 0U; index < 3U; ++index) { covariance[index * 4U] = pv[index]; }
        pr = Navigation_UpdateVector(&context->augmented, &context->augmented_work,
            position, covariance, NavigationPosition, (double)measurement_us * 1.0e-6, 16.266);
        for (index = 0U; index < 3U; ++index) { covariance[index * 4U] = vv[index]; }
        vr = Navigation_UpdateVector(&context->augmented, &context->augmented_work,
            velocity, covariance, NavigationVelocity, (double)measurement_us * 1.0e-6, 16.266);
        if (pr != NavigationOk || vr != NavigationOk) { result = HOST_REJECTED; }
    }
    else { return HOST_INVALID; }
    context->gnss_seen = 1U; context->gnss_timestamp_us = measurement_us;
    if (HostNavigation_OutputRefresh(context) != HOST_OK) { return HOST_NUMERIC; }
    return result;
}

HostNavigationResult HostNavigation_Snapshot(void *memory, double output[13])
{
    HostNavigationContext *context = memory;
    if (context == NULL || output == NULL) { return HOST_INVALID; }
    memcpy(output, context->output, sizeof(context->output));
    return context->started ? HOST_OK : HOST_WAITING;
}

HostNavigationResult HostNavigation_Barometer(void *memory, uint64_t measurement_us,
    uint64_t arrival_us, double altitude_m, double std_m)
{
    HostNavigationContext *context=memory;
    HostNavigationResult result=HOST_OK;
    if(context==NULL || !context->started || !isfinite(altitude_m) || !isfinite(std_m) ||
       std_m<=0.0 || fabs(altitude_m)>1.0e10 || std_m>1.0e10) { return HOST_INVALID; }
    if(context->kind==0 || context->kind>=4) { return HOST_UNSUPPORTED; }
    if(measurement_us>arrival_us || arrival_us>context->timestamp_us ||
       (context->barometer_seen && measurement_us<=context->barometer_timestamp_us) ||
       (context->kind==3 && measurement_us!=context->timestamp_us)) { return HOST_STALE; }
    if(context->kind==2)
    {
        if(NavigationKf_UpdateBaroAltitude(&context->kf,(float)altitude_m,
            (float)(std_m*std_m))>NAV_KF_UPDATE_SOFT_WEIGHTED) { result=HOST_REJECTED; }
    }
    else if(context->kind==1)
    {
        NavigationSf6Measurement sample={0}; uint64_t boundary;
        sample.measurement_us=measurement_us; sample.receive_us=arrival_us;
        sample.sequence=(uint32_t)(measurement_us/1000U); sample.group=4U;
        sample.observation[0]=(float)altitude_m;
        if(NavigationSf6_Update(&context->sf,&sample,&boundary)!=NAV_SF6_OK) { result=HOST_REJECTED; }
    }
    else
    {
        NavigationEskfMeasurement sample={0}; NavigationEskfOutcome outcome;
        sample.group=4U; sample.physically_valid=1U;
        sample.observation[0]=(float)altitude_m; sample.variance[0]=(float)(std_m*std_m);
        if(NavigationEskf_UpdateRevision2(&context->eskf,&context->eskf_work,
            &context->eskf_config,&sample,&outcome)>NAV_ESKF_SOFT_WEIGHTED) { result=HOST_REJECTED; }
    }
    context->barometer_seen=1U; context->barometer_timestamp_us=measurement_us;
    if(HostNavigation_OutputRefresh(context)!=HOST_OK) { return HOST_NUMERIC; }
    return result;
}

HostNavigationResult HostNavigation_Magnetic(void *memory, uint64_t measurement_us,
    uint64_t arrival_us, const double field_s_t[3], double std_t)
{
    HostNavigationContext *context=memory;
    NavigationMagneticSample sample={0}; NavigationResult result; unsigned index;
    if(context==NULL || !context->started || !HostNavigation_VectorValid(field_s_t,3U) ||
       !isfinite(std_t) || std_t<=0.0 || std_t>1.0) { return HOST_INVALID; }
    if(context->kind!=4 && context->kind!=6) { return HOST_UNSUPPORTED; }
    if(measurement_us>arrival_us || arrival_us>context->timestamp_us ||
       measurement_us!=context->timestamp_us ||
       (context->magnetic_seen && measurement_us<=context->magnetic_timestamp_us)) { return HOST_STALE; }
    for(index=0U;index<3U;++index)
    {
        sample.corrected_sensor_uT[index]=field_s_t[index]*1.0e6;
        sample.covariance_sensor_uT2[index*4U]=std_t*std_t*1.0e12;
    }
    sample.time_s=(double)measurement_us*1.0e-6;
    sample.sensor_frame=1U; sample.calibration=1U;
    sample.reference_strength_uT=context->magnetic_strength;
    result=Navigation_UpdateMagnetic(&context->augmented,&context->augmented_work,&sample,16.266);
    context->magnetic_seen=1U; context->magnetic_timestamp_us=measurement_us;
    if(HostNavigation_OutputRefresh(context)!=HOST_OK) { return HOST_NUMERIC; }
    return result==NavigationOk ? HOST_OK : result==NavigationNumericError ? HOST_NUMERIC : HOST_REJECTED;
}
